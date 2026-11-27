"""Publish reviewed face-linked actions and withheld scene descriptions from a private album ledger to a local preview."""

import argparse
import hashlib
import json
import math
import os
import re
import runpy
import sqlite3
import tempfile
import time
from contextlib import closing
from html import escape
from pathlib import Path
from urllib.parse import quote
from uuid import UUID

from PIL import Image, ImageOps

from journey_faces import complete_faces
from collage_catalogue import catalogue, filter_timeline, regular_grid
from caption_participants import age_status, attach, fingerprint
from openlabel_album import attach_ocr, build_scene, card, link_depicted_faces, persist, stable_id, validate_scenes


def read(path: Path):
    return json.loads(path.read_text())


def atomic_page(path: Path, content: str) -> None:
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as tmp:
        tmp.write(content)
    Path(tmp.name).replace(path)


def card_json(cards: list[dict]) -> str:
    """Encode private card data for a standalone HTML script element."""
    return json.dumps(cards, ensure_ascii=False).replace("<", "\\u003c")


def select_together(cards: dict, people: list[str]) -> list[dict]:
    """Select original photos with distinct reviewed subjects for all requested people."""
    requested = set(people)
    if len(requested) < 2 or len(requested) != len(people) or not all(requested):
        raise ValueError("Choose at least two distinct person IDs")
    selected = []
    for item in cards.values():
        if item["media_type"] != "Photo":
            continue
        actors = (item["faces"][c["subject"]] for c in item["claims"] + item["individual"])
        subjects = {face["person_id"] for face in actors if not face.get("depicted_in")}
        if requested <= subjects:
            # The source age check belongs to the original journey subject. Carry only date certainty.
            copy = dict(item)
            copy.pop("date_conflict", None)
            copy["journey_date_note"] = {
                "confirmed": "Confirmed date in the source journey.",
                "conflict": "The source journey flags a conflict with this recorded date.",
                "compatible": "The source review found the recorded date plausible.",
            }.get(item["date_status"], "The capture date is uncertain.")
            selected.append(copy)
    return sorted(selected, key=lambda item: (item["date"], item["asset"]))


def render_review(template: str, cards: list[dict], title: str, intro: str) -> str:
    """Render one private scope with the shared caption and face controls."""
    # Insert the card payload last so private caption text is never treated as markup.
    header, body = template.split("PILOT_JSON")
    labels = {"REVIEW_TITLE": title, "REVIEW_INTRO": intro}
    header = re.sub(r"REVIEW_TITLE|REVIEW_INTRO", lambda m: escape(labels[m[0]]), header)
    return header + card_json(cards) + body


def journey_page(path: Path, cards: dict, styles: str, renderer: str, members: list, types: dict) -> str:
    """Bind action tags to the existing chronological cards, preserving the album layout."""
    original = path.read_text()
    start, end = "<!-- BEGIN journey face cards -->", "<!-- END journey face cards -->"
    if start in original or end in original:
        if original.count(start) != 1 or original.count(end) != 1:
            raise ValueError("Invalid journey cards block")
        before, rest = original.split(start)
        _, after = rest.split(end)
        original = before + after
    collages = {asset for asset in members if types.get(asset, {}).get("type") == "Collage"}
    page = filter_timeline(original, collages, len(members))
    link = '<p id="openlabel-pilot"><a href="OpenLABEL%20album%20review.html">Review face and action tags</a></p>'
    if link not in page:
        if page.count("</h1>") != 1:
            raise ValueError("Could not locate the album heading")
        page = page.replace("</h1>", "</h1>" + link)
    if page.count("</html>") != 1:
        raise ValueError("Could not locate end of album")
    visible = [card for asset, card in cards.items() if asset not in collages]
    fragment = (f'{start}<style>{styles}</style><script id="journey-scenes" type="application/json">'
                f'{card_json(visible)}</script><script>{renderer}</script>{end}')
    return page.replace("</html>", fragment + "</html>")


def publish(root: Path, schema: Path, current: dict, conn, jobs_path: Path | None = None,
            timeline: Path | None = None, together: list[str] | None = None) -> dict:
    if timeline is None:
        # Rebuild a previously enabled timeline when refreshing names or action evidence.
        enabled = [p for p in root.glob("*.html") if "<!-- BEGIN journey face cards -->" in p.read_text()]
        if len(enabled) == 1:
            timeline, = enabled
        elif enabled:
            raise ValueError("Multiple journey pages found; select one with --timeline")
    if timeline and timeline.resolve().parent != root.resolve():
        raise ValueError("Timeline and review must share their private album directory")
    started = time.perf_counter()
    album = read(root / "album-after-owner-correction.json")
    if current["album"] != album["id"] or set(current["members"]) != set(album["members"]):
        raise ValueError("Refresh the album inventory before publishing")
    if not current["private"]:
        raise ValueError("Private review requires an owner-only album")
    if together and any(not (current["names"].get(pid) or "").strip() for pid in together):
        raise ValueError("Choose current confirmed person IDs for this private snapshot")
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
    group_path = root / "journey-face-actions.json"
    group_reviews = read(group_path) if group_path.exists() else {}
    if group_reviews.keys() - set(current["members"]):
        raise ValueError("Per-person review contains assets outside this album")
    if set(current.get("ocr", {})) != {row["asset"] for row in reviewed}:
        raise ValueError("Refresh the source snapshot to read current Immich OCR for this album")
    ledger = root / "nikhil-life-stage-backfill/jobs.sqlite3"
    scenes, cards, expected = {}, {}, {}
    build_durations = []
    group_durations = []
    ocr_durations = []
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
                display_parts = [parts[0], audit["literal"]] if audit and "source_literal" in audit else parts
                expected[asset].append("".join(
                    (current["names"].get(p["person_id"]) or current["names"].get(p["namespace"]+":"+p["face_id"])
                     or "Unnamed person") if isinstance(p, dict) else p
                    for p in display_parts))
                labels.add(label)
                actions.append(parts)
            if not audit and labels != set(row["actions"]):
                raise ValueError("Incomplete reviewed action set")
            scenes[asset] = build_scene(asset, actions, regions, width, height, audit)
            prior = recorded[asset]
            inputs = [audit.get("literal", audit.get("scene"))] if audit else list(row["actions"].values())
            decision_path = root / "caption-participants" / (asset + ".json")
            decision = read(decision_path) if decision_path.is_file() else None
            source_inputs = [audit["source_literal"]] if audit and "source_literal" in audit else inputs
            corrections = [{"phrase": m["words"], "finding": m["reason"]}
                           for m in (decision or {}).get("mentions", []) if m.get("reason")]
            notes = [c["finding"] for c in corrections]
            if jobs_path:
                jobs.append({"asset":asset, "captions":source_inputs, "image":str(path),
                             "regions":list(regions.values()), "subject_face_id":(audit or {}).get("face_id"),
                             "subject_namespace":(audit or {}).get("namespace"),
                             "subject_name":next(iter(labels)) if audit and len(labels) == 1 else None,
                             "corrections":corrections if (audit or {}).get("face_id") else []})
            if audit and "source_literal" in audit:
                if not decision or decision["caption_hash"] != fingerprint(source_inputs) or not notes:
                    raise ValueError("Missing original correction evidence")
                digest = hashlib.sha256(json.dumps(decision, sort_keys=True).encode()).hexdigest()
                if digest != audit["review_digest"] or regions[audit["namespace"], audit["face_id"]]["box"] != audit["review_box"]:
                    raise ValueError("Correction evidence changed since reconciliation")
                # Raw sources survive in the ledger and previous scene revisions. Display the accepted claims.
                scenes[asset]["openlabel"].setdefault("contexts", {})["2"] = {
                    "name": "Caption sources", "type": "reconciliation_evidence", "context_data": {"text": [
                        {"name":"source_literal","val":audit["source_literal"]},
                        {"name":"review","val":" ".join(notes)}, {"name":"digest","val":digest}]}}
                decision = {"caption_hash": fingerprint(inputs), "mentions": audit["accepted_mentions"]}
            if decision:
                attach(scenes[asset], asset, inputs, regions, decision)
            media_type = media_types.get(asset, {}).get("type", "Photo")
            if media_type != "Collage":
                started_group = time.perf_counter()
                primary = card(scenes[asset], current["names"])
                complete_faces(scenes[asset], asset, regions, {c["subject"] for c in primary["claims"]},
                               group_reviews.get(asset, {}))
                if sum(ns == "immich" for ns, _ in regions) > 1:
                    group_durations.append(time.perf_counter() - started_group)
            if media_type == "Collage":
                layout = root / "collage-layouts" / (asset + ".json")
                if layout.is_file():
                    geometry = read(layout)
                else:
                    with Image.open(path) as original:
                        geometry = regular_grid(original)
                if geometry:
                    catalogue(scenes[asset], asset, geometry, regions)
            media_path = root / "depiction-media" / (asset + ".json")
            if media_path.is_file():
                media = read(media_path)
                validate_scenes({asset: media}, schema)
                link_depicted_faces(scenes[asset], media)
            ocr_started = time.perf_counter()
            attach_ocr(scenes[asset], current["ocr"][asset])
            ocr_durations.append(time.perf_counter() - ocr_started)
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
        if cards[asset]["ocr"] != current["ocr"][asset]:
            raise ValueError("Stored OCR tags differ from the Immich snapshot")
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
    if together:
        pair_started = time.perf_counter()
        selected = select_together(cards, together)
        selection_time = time.perf_counter() - pair_started
    page = Path(__file__).with_name("openlabel_review.html").read_text()
    renderer = Path(__file__).with_name("album_cards.js").read_text()
    styles = Path(__file__).with_name("album_card_links.css").read_text()
    page = page.replace("SHARED_CARD_STYLES", styles).replace("ALBUM_CARD_RENDERER", renderer)
    if timeline:
        enriched = journey_page(timeline, cards, styles, renderer, current["members"], media_types)
        if enriched != timeline.read_text():
            atomic_page(timeline, enriched)
    instructions = "Select a name to see what that person is doing. Select an action to highlight its participants."
    atomic_page(root / "OpenLABEL album review.html", render_review(page, list(cards.values()),
                                                                  "Face and action review", instructions))
    pair_result = {}
    if together:
        pair_started = time.perf_counter()
        names = sorted(current["names"][pid] for pid in together)
        title = " and ".join(names) + " together"
        label = f"{len(selected)} matching photos in the reviewed collection. " if selected else (
            "No reviewed photo in this collection has an action for every selected person. ")
        filename = "Together-" + stable_id(album["id"], *sorted(together)) + ".html"
        atomic_page(root / filename, render_review(page, selected, title, label + instructions))
        pair_result = {"together_page": filename, "together_photos": len(selected),
                       "selection_and_render_ms": round((time.perf_counter() - pair_started + selection_time) * 1000, 2)}
    if jobs_path:
        atomic_page(jobs_path, "".join(json.dumps(job) + "\n" for job in jobs))
    groups = [c for a, c in cards.items() if c["media_type"] != "Collage" and
              sum(r["namespace"] == "immich" for r in current["regions"].get(a, [])) > 1]
    partial = sum(any("action_withheld" in face for face in c["faces"].values()) for c in groups)
    return {**pair_result, "ocr_p95": sorted(ocr_durations)[math.ceil(.95*len(ocr_durations))-1],
            "ocr_photos": sum(bool(c["ocr"]) for c in cards.values()),
            "ocr_regions": sum(len(c["ocr"]) for c in cards.values()), "album_highlights": len(album["members"]), "reviewed_photos": len(stored),
            "faces": sum(len(c["faces"]) for c in cards.values()),
            "scene_only": sum("scene" in c for c in cards.values()),
            "actions": sum(len(scene["openlabel"].get("actions", {})) for scene in stored.values()),
            "seconds": round(time.perf_counter()-started,3), "build_p95": sorted(build_durations)[math.ceil(.95*len(build_durations))-1],
            "model_calls": 0, "group_photos": len(groups), "group_partial": partial,
            "additional_face_actions": sum(len(c["individual"]) for c in groups),
            "group_p95": sorted(group_durations)[math.ceil(.95*len(group_durations))-1] if group_durations else 0}


if __name__ == "__main__":
    import psycopg

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("album_directory", type=Path)
    parser.add_argument("current_sources", type=Path, help="Private authorized face and album snapshot")
    parser.add_argument("schema", type=Path, help="Pinned OpenLABEL 1.0.0 JSON Schema")
    parser.add_argument("--participant-jobs", type=Path, help="Write private JSONL jobs for the reusable local face matcher")
    parser.add_argument("--timeline", type=Path, help="Refresh face-linked captions in the existing private HTML album")
    parser.add_argument("--metrics-host", help="Existing private node-exporter textfile collector")
    parser.add_argument("--together", nargs="+", type=UUID, metavar="PERSON_ID",
                        help="Publish an additional private same-photo view for these confirmed people")
    args = parser.parse_args()
    os.umask(0o077)
    with psycopg.connect(autocommit=True) as connection:
        result = publish(args.album_directory, args.schema, read(args.current_sources), connection, args.participant_jobs, args.timeline,
                         [str(pid) for pid in args.together] if args.together else None)
    if args.metrics_host:
        metrics = runpy.run_path(str(Path(__file__).resolve().parents[1] / "photo-stage-metrics.py"))
        stages = [("openlabel-pilot", result["reviewed_photos"], result["scene_only"], result["build_p95"]),
                  ("journey-group-actions", result["group_photos"], result["group_partial"], result["group_p95"]),
                  ("immich-ocr-tags", result["reviewed_photos"], 0, result["ocr_p95"])]
        for name, total, partial, duration in stages:
            stage = f'stage="{name}"'
            counts = {"complete": total - partial, "withheld": partial}
            report = []
            for state in metrics["STATES"]:
                count = counts.get(state, 0)
                report.append(f'knowledge_index_photo_stage_items{{{stage},state="{state}"}} {count}')
            report.extend([
                f'knowledge_index_photo_stage_completed_total{{{stage}}} {counts["complete"]}',
                f'knowledge_index_photo_stage_updated_timestamp_seconds{{{stage}}} {time.time()}',
                f'knowledge_index_photo_stage_phase_p95_seconds{{{stage},phase="build_scene"}} {duration}',
            ])
            # Use the shared metric descriptors so node-exporter can merge both textfiles.
            names = {line.split("{")[0] for line in report}
            headers = [line for name in sorted(names) for line in
                       (f"# HELP {name} {metrics['HELP'][name][1]}", f"# TYPE {name} {metrics['HELP'][name][0]}")]
            metrics["publish_textfile"]("\n".join(headers + report) + "\n", args.metrics_host, name)
    print(json.dumps(result))
