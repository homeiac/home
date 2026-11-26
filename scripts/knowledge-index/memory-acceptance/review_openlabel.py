"""Publish reviewed face-linked actions and withheld scene descriptions from a private album ledger to a local preview."""

import argparse
import json
import math
import os
import runpy
import sqlite3
import tempfile
import time
from contextlib import closing
from pathlib import Path
from urllib.parse import quote
from uuid import UUID

from PIL import Image, ImageOps

from collage_catalogue import catalogue, filter_timeline, regular_grid
from caption_participants import age_status, attach
from openlabel_album import build_scene, card, persist, validate_scenes


def read(path: Path):
    return json.loads(path.read_text())


def atomic_page(path: Path, content: str) -> None:
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as tmp:
        tmp.write(content)
    Path(tmp.name).replace(path)


def publish(root: Path, schema: Path, current: dict, conn, jobs_path: Path | None = None) -> dict:
    started = time.perf_counter()
    album = read(root / "album-after-owner-correction.json")
    if current["album"] != album["id"] or set(current["members"]) != set(album["members"]):
        raise ValueError("Refresh the album inventory before publishing")
    if not current["private"]:
        raise ValueError("Private review requires an owner-only album")
    pilot = root / "album-life-stage-pilot"
    reviewed = read(pilot / "group-actions/verified-actions.json")
    if not reviewed:
        raise ValueError("The declared pilot contains no reviewed photos")
    manifest = root / "album-reviewed-spans.json"
    marked = read(manifest) if manifest.is_file() else {}
    recorded = {row["asset"]: row for row in read(pilot / "review-results.json")["photos"]}
    media_types = read(pilot / "composite-types.json")
    birth_year = read(root / "timeline-age-evidence.json")["birth_year"]
    if manifest.is_file():
        groups = {row["asset"] for row in reviewed}
        if groups & marked.keys() or groups | marked.keys() != set(current["members"]):
            raise ValueError("Span review must cover exactly the remaining album members")
        for asset, audit in marked.items():
            prior = recorded[asset]
            if (audit.get("reason") or None) != (prior.get("local_skip") or None):
                raise ValueError("Ambiguous-face disposition changed")
            reviewed.append({"asset": asset, "date": prior["date"]})
    ledger = root / "nikhil-life-stage-backfill/jobs.sqlite3"
    scenes, cards, expected = {}, {}, {}
    build_durations = []
    jobs = []
    with closing(sqlite3.connect(ledger.resolve().as_uri()+"?mode=ro", uri=True)) as db:
        db.execute("BEGIN")
        for row in sorted(reviewed, key=lambda item: (item["date"], item["asset"])):
            card_started = time.perf_counter()
            asset = str(UUID(row["asset"]))
            if asset in scenes or asset not in current["members"]:
                raise ValueError("Reviewed asset duplicated or outside album")
            path, = (root / "thumbnails").glob(asset+".*")
            with Image.open(path) as image:
                width, height = ImageOps.exif_transpose(image).size
            audit = marked.get(asset)
            source = "marked subject" if audit else "verified group action"
            regions = {(r["namespace"], r["face_id"]): r for r in current["regions"].get(asset, [])}
            actions = []
            labels = set()
            expected[asset] = []
            for label, namespace, face, raw in db.execute("""SELECT label,face_namespace,face_id,
                    action_parts FROM face_actions WHERE asset=? AND source=?
                    ORDER BY label""", (asset, source)):
                parts = [part for part in json.loads(raw) if part != ""]
                if (parts[0]["namespace"], parts[0]["face_id"], parts[0]["fallback"]) != (namespace, face, label):
                    raise ValueError("Saved actor does not match the ledger face")
                original = "".join(p["fallback"] if isinstance(p, dict) else p for p in parts)
                if not audit and original != label+" "+row["actions"][label]:
                    raise ValueError("Saved action differs from the reviewed caption")
                expected[asset].append("".join(
                    (current["names"].get(p["person_id"]) or current["names"].get(p["namespace"]+":"+p["face_id"])
                     or "Unnamed person") if isinstance(p, dict) else p
                    for p in parts))
                labels.add(label)
                actions.append(parts)
            if not audit and labels != set(row["actions"]):
                raise ValueError("Incomplete reviewed action set")
            scenes[asset] = build_scene(asset, actions, regions, width, height, audit)
            prior = recorded[asset]
            inputs = [audit.get("literal", audit.get("scene"))] if audit else list(row["actions"].values())
            if jobs_path:
                jobs.append({"asset":asset, "captions":inputs, "image":str(path),
                             "regions":list(regions.values()), "subject_face_id":(audit or {}).get("face_id")})
            decision_path = root / "caption-participants" / (asset + ".json")
            if decision_path.is_file():
                attach(scenes[asset], asset, inputs, regions, read(decision_path))
            media_type = media_types.get(asset, {}).get("type", "Photo")
            if media_type == "Collage":
                layout = root / "collage-layouts" / (asset + ".json")
                if layout.is_file():
                    geometry = read(layout)
                else:
                    with Image.open(path) as original:
                        geometry = regular_grid(original)
                if geometry:
                    catalogue(scenes[asset], asset, geometry, regions)
            status = age_status(prior, birth_year)
            if status == "conflict":
                if prior["date"] != row["date"]:
                    raise ValueError("Recorded date differs from the life-stage review")
                facts = {"recorded_date": prior["date"], "date_source": prior["date_source"],
                         "visual_stage": prior["accepted"]["stage"], "birth_year": str(birth_year)}
                contexts = scenes[asset]["openlabel"].setdefault("contexts", {})
                contexts["1"] = {"type": "capture_date_conflict", "name": "Capture date disputed",
                                 "context_data": {"text": [{"name": k, "val": v} for k, v in facts.items()]}}
            base_url = current["album_url"].rstrip("/")
            if media_type == "Collage":
                base_url = base_url.rsplit("/albums/", 1)[0]
            cards[asset] = {"asset": asset, "date": row["date"], "image": "thumbnails/"+quote(path.name),
                            "date_status": status, "media_type": media_type, "original": base_url+"/photos/"+asset}
            build_durations.append(time.perf_counter() - card_started)
    validate_scenes(scenes, schema)
    def check_caption(asset: str, scene: dict) -> None:
        cards[asset].update(card(scene, current["names"]))
        captions = ["".join(s.get("source_words", cards[asset]["faces"][s["face"]]["name"]) if "face" in s else
                            s.get("text", s.get("verb")) for s in claim["spans"])
                    for claim in cards[asset]["claims"]]
        if sorted(captions) != sorted(expected[asset]):
            raise ValueError("Stored scene changed the reviewed caption")
    for asset, scene in scenes.items():
        check_caption(asset, scene)
    stored = persist(conn, album["id"], scenes)
    for asset, scene in stored.items():
        check_caption(asset, scene)
    page = Path(__file__).with_name("openlabel_review.html").read_text()
    payload = json.dumps(list(cards.values()), ensure_ascii=False).replace("<","\\u003c")
    atomic_page(root / "OpenLABEL album review.html", page.replace("PILOT_JSON", payload))
    if jobs_path:
        atomic_page(jobs_path, "".join(json.dumps(job) + "\n" for job in jobs))
    return {"album_highlights": len(album["members"]), "reviewed_photos": len(stored),
            "faces": sum(len(c["faces"]) for c in cards.values()),
            "scene_only": sum("scene" in c for c in cards.values()),
            "actions": sum(len(scene["openlabel"].get("actions", {})) for scene in stored.values()),
            "seconds": round(time.perf_counter()-started,3), "build_p95": sorted(build_durations)[math.ceil(.95*len(build_durations))-1],
            "model_calls": 0}


if __name__ == "__main__":
    import psycopg

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("album_directory", type=Path)
    parser.add_argument("current_sources", type=Path, help="Private authorized face and album snapshot")
    parser.add_argument("schema", type=Path, help="Pinned OpenLABEL 1.0.0 JSON Schema")
    parser.add_argument("--participant-jobs", type=Path, help="Write private JSONL jobs for the reusable local face matcher")
    parser.add_argument("--timeline", type=Path, help="Link the preview from the existing private HTML album")
    parser.add_argument("--metrics-host", help="Existing private node-exporter textfile collector")
    args = parser.parse_args()
    os.umask(0o077)
    with psycopg.connect(autocommit=True) as connection:
        result = publish(args.album_directory, args.schema, read(args.current_sources), connection, args.participant_jobs)
    if args.timeline:
        if args.timeline.resolve().parent != args.album_directory.resolve():
            raise ValueError("Timeline and pilot must share their private album directory")
        page = args.timeline.read_text()
        link = '<p id="openlabel-pilot"><a href="OpenLABEL%20album%20review.html">Review face and action tags</a></p>'
        original = page
        inventory = read(args.album_directory / "album-after-owner-correction.json")["members"]
        types = read(args.album_directory / "album-life-stage-pilot/composite-types.json")
        collages = {a for a in inventory if types.get(a, {}).get("type") == "Collage"}
        page = filter_timeline(page, collages, len(inventory))
        if link not in page:
            if page.count("</h1>") != 1:
                raise ValueError("Could not locate the album heading")
            page = page.replace("</h1>", "</h1>"+link)
        if original != page:
            atomic_page(args.timeline, page)
    if args.metrics_host:
        metrics = runpy.run_path(str(Path(__file__).resolve().parents[1] / "photo-stage-metrics.py"))
        stage = 'stage="openlabel-pilot"'
        report = []
        counts = {"complete": result["reviewed_photos"] - result["scene_only"],
                  "withheld": result["scene_only"]}
        for state in metrics["STATES"]:
            count = counts.get(state, 0)
            report.append(f'knowledge_index_photo_stage_items{{{stage},state="{state}"}} {count}')
        report.extend([
            f'knowledge_index_photo_stage_completed_total{{{stage}}} {counts["complete"]}',
            f'knowledge_index_photo_stage_updated_timestamp_seconds{{{stage}}} {time.time()}',
            f'knowledge_index_photo_stage_phase_p95_seconds{{{stage},phase="build_scene"}} {result["build_p95"]}',
        ])
        # Use the shared metric descriptors so node-exporter can merge both textfiles.
        names = {line.split("{")[0] for line in report}
        headers = [line for name in sorted(names) for line in
                   (f"# HELP {name} {metrics['HELP'][name][1]}", f"# TYPE {name} {metrics['HELP'][name][0]}")]
        metrics["publish_textfile"]("\n".join(headers + report) + "\n", args.metrics_host, "openlabel-pilot")
    print(json.dumps(result))
