"""Freeze an owner-scoped Immich library for private OCR and per-face processing."""

import argparse
from contextlib import closing
import importlib
import fcntl
import json
import os
import re
from pathlib import Path
import sqlite3
import sys
from uuid import UUID

from openlabel_album import attach_ocr, ocr_regions
from review_openlabel import read

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
claims = importlib.import_module("life-stage-claims")


def connect(root):
    db = sqlite3.connect(root / "library.sqlite3", timeout=120)
    db.execute("PRAGMA foreign_keys=ON")
    return db


def initialize(db):
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS photos(id TEXT PRIMARY KEY, path TEXT NOT NULL, day TEXT,
            checksum TEXT NOT NULL, ocr_done INTEGER NOT NULL, tags TEXT NOT NULL, region_count INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS jobs(asset TEXT PRIMARY KEY, photo TEXT NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
            day TEXT NOT NULL, input TEXT NOT NULL, person TEXT, name TEXT, status TEXT NOT NULL,
            outcome TEXT, attempts INTEGER NOT NULL DEFAULT 0);
        CREATE INDEX IF NOT EXISTS job_order ON jobs(status,day,asset);
        CREATE INDEX IF NOT EXISTS job_photo ON jobs(photo);
        CREATE TABLE IF NOT EXISTS reviewed(photo TEXT PRIMARY KEY REFERENCES photos(id) ON DELETE CASCADE, card TEXT NOT NULL);
        CREATE VIRTUAL TABLE IF NOT EXISTS words USING fts5(photo UNINDEXED, text, names);
        CREATE TABLE IF NOT EXISTS scope(owner TEXT, library TEXT);
    """
    )
    claims.initialize(db)


def inventory(owner, library, pg):
    # All three readings use the same MVCC snapshot. Each result is bound to a scoped photo.
    scope = f"""a."ownerId"='{UUID(owner)}' AND a."libraryId"='{UUID(library)}'
        AND a.type='IMAGE' AND a.visibility='timeline' AND a."deletedAt" IS NULL AND NOT a."isOffline" """
    return pg(
        f"""BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
        SELECT json_build_array(a.id,a."originalPath",to_char(a."localDateTime",'YYYY-MM-DD'),encode(a.checksum,'hex'),
          s."ocrAt" IS NOT NULL,
          coalesce((SELECT json_agg(json_build_object('id',o.id,'text',o.text,'polygon',
            ARRAY[o.x1,o.y1,o.x2,o.y2,o.x3,o.y3,o.x4,o.y4]) ORDER BY o.y1,o.x1,o.id)
            FROM asset_ocr o WHERE o."assetId"=a.id AND o."isVisible" AND btrim(o.text)<>''),'[]'),
          coalesce((SELECT json_agg(json_build_array(f.id,f."personGroupId",p.name,
            ARRAY[f."boundingBoxX1"::float/f."imageWidth",f."boundingBoxY1"::float/f."imageHeight",
                  f."boundingBoxX2"::float/f."imageWidth",f."boundingBoxY2"::float/f."imageHeight"]) ORDER BY f.id)
            FROM asset_face f LEFT JOIN person p ON p."personGroupId"=f."personGroupId" AND p."ownerId"=f."ownerId"
            WHERE f."assetId"=a.id AND f."ownerId"=a."ownerId" AND f."deletedAt" IS NULL
            AND f."isVisible" AND NOT coalesce(p."isHidden",false) AND f."imageWidth">0 AND f."imageHeight">0),'[]'))
        FROM asset a LEFT JOIN asset_job_status s ON s."assetId"=a.id WHERE {scope} ORDER BY a.id;
        COMMIT;"""
    )


def reuse_results(db, pilot):
    old = pilot / "nikhil-life-stage-backfill/jobs.sqlite3"
    members = set(read(pilot / "album-after-owner-correction.json")["members"])
    with closing(sqlite3.connect(old.as_uri() + "?mode=ro", uri=True)) as history:
        for asset, face, raw, result, parts in history.execute(
            """
            SELECT j.asset,f.face_id,j.input,j.outcome,f.action_parts FROM jobs j JOIN face_actions f USING(asset)
            WHERE j.status='complete' AND f.face_namespace='immich' AND f.source='marked subject'"""
        ):
            source, value = json.loads(raw), json.loads(result)
            if not source.get("box") or value.get("error") or asset in members:
                continue
            row = db.execute(
                "SELECT input FROM jobs WHERE asset=? AND photo=? AND status IN ('pending','reused')",
                (face, asset),
            ).fetchone()
            if not row:
                continue
            current = json.loads(row[0])
            if (
                current["path"] != source["path"]
                or max(abs(a - b) for a, b in zip(source["box"], current["box"]))
                > 0.00001
            ):
                continue
            result = {
                "stage": value["stage"],
                "confidence": value["confidence"],
                "action": value["scene"],
                "parts": json.loads(parts),
                "source": "saved marked-face observation",
            }
            db.execute(
                "UPDATE jobs SET status='reused',outcome=? WHERE asset=?",
                (json.dumps(result), face),
            )
    page = (pilot / "OpenLABEL album review.html").read_text()
    cards = json.loads(
        re.search(
            r'<script id="scenes" type="application/json">(.*?)</script>', page, re.S
        )[1]
    )
    stages = {
        item["asset"]: item.get("accepted") or {}
        for item in read(pilot / "album-life-stage-pilot/review-results.json")["photos"]
    }
    marked = read(pilot / "album-reviewed-spans.json")
    db.execute("DELETE FROM reviewed")
    for card in cards:
        asset = card["asset"]
        if (
            asset not in members
            or not db.execute("SELECT 1 FROM photos WHERE id=?", (asset,)).fetchone()
        ):
            continue
        face_rows = {
            fid: json.loads(raw)["box"]
            for fid, raw in db.execute(
                "SELECT asset,input FROM jobs WHERE photo=?", (asset,)
            )
        }
        current = True
        for face in card["faces"].values():
            if face["face_namespace"] != "immich":
                continue
            box = face_rows.get(face["face_id"])
            x, y, w, h = face["box"]
            normalized = [
                (x - w / 2) / card["width"],
                (y - h / 2) / card["height"],
                (x + w / 2) / card["width"],
                (y + h / 2) / card["height"],
            ]
            if (
                not box
                or max(
                    abs(max(0, min(1, a)) - max(0, min(1, b)))
                    for a, b in zip(box, normalized)
                )
                > 0.00001
            ):
                current = False
        if not current:
            continue
        db.execute("INSERT INTO reviewed VALUES(?,?)", (asset, json.dumps(card)))
        for uid, face in card["faces"].items():
            fid = face.get("immich_face_id") or (
                face["face_id"] if face["face_namespace"] == "immich" else None
            )
            if fid not in face_rows:
                continue
            actions = [
                claim
                for claim in [*card["claims"], *card["individual"]]
                if claim["subject"] == uid
            ]
            result = {
                "source": "reviewed album",
                "reviewed_action": True,
                "action": None,
            }
            stage_ref = marked.get(asset, {})
            has_stage = (
                stage_ref.get("face_id") == face["face_id"]
                and stage_ref.get("namespace") == face["face_namespace"]
            )
            if has_stage and stages.get(asset, {}).get("stage"):
                result.update(
                    stage=stages[asset]["stage"],
                    confidence=stages[asset].get("confidence", "medium"),
                )
            state = "pending"
            if card["media_type"] == "Collage" or face.get("action_withheld"):
                state = "withheld"
                result["reason"] = face.get(
                    "action_withheld", "Composite image; see reviewed panels"
                )
            elif actions:
                result["reviewed_action"] = True
                result["action"] = (
                    "reviewed"  # Display the original role-linked spans from the reviewed card.
                )
                if "stage" in result:
                    state = "reused"
            else:
                result["reviewed_action"] = False
            db.execute(
                "UPDATE jobs SET status=?,outcome=? WHERE photo=? AND asset=? AND status IN ('pending','reused')",
                (state, json.dumps(result), asset, fid),
            )
    return members


def prepare(root, pilot):
    sys.path.insert(0, str(pilot / "reproduction"))
    from common import pg, api_js

    owner, library = read(pilot / "scope.json")
    if api_js("console.log(JSON.stringify((await api('/users/me')).id))") != owner:
        raise ValueError("Immich owner changed")
    rows = inventory(owner, library, pg)
    if not rows:
        raise ValueError("Empty inventory; previous snapshot retained")
    with closing(connect(root)) as db:
        initialize(db)
        with db:
            db.execute("BEGIN IMMEDIATE")
            prior = db.execute("SELECT * FROM scope").fetchone()
            if prior and prior != (owner, library):
                raise ValueError("Use a separate checkpoint for each owner/library")
            if not prior:
                db.execute("INSERT INTO scope VALUES(?,?)", (owner, library))
            db.execute("CREATE TEMP TABLE seen_photo(id TEXT PRIMARY KEY)")
            db.execute("CREATE TEMP TABLE seen_face(id TEXT PRIMARY KEY)")
            for asset, path, day, sha, done, regions, faces in rows:
                if not path.startswith("/external/gphotos/"):
                    raise ValueError("Unknown thumbnail path mapping")
                path = path.removeprefix("/external/gphotos/")
                scene = {"openlabel": {}}
                attach_ocr(scene, regions)
                if ocr_regions(scene["openlabel"]) != regions:
                    raise ValueError("OCR projection differs from source")
                db.execute("INSERT INTO seen_photo VALUES(?)", (asset,))
                db.execute(
                    """INSERT INTO photos VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                    path=excluded.path,day=excluded.day,checksum=excluded.checksum,ocr_done=excluded.ocr_done,
                    tags=excluded.tags,region_count=excluded.region_count""",
                    (
                        asset,
                        path,
                        day,
                        sha,
                        done,
                        json.dumps(
                            scene["openlabel"].get("tags", {}), ensure_ascii=False
                        ),
                        len(regions),
                    ),
                )
                for face, person, name, box in faces:
                    db.execute("INSERT INTO seen_face VALUES(?)", (face,))
                    source = json.dumps(
                        dict(id=face, photo=asset, path=path, checksum=sha, box=box)
                    )
                    db.execute(
                        """DELETE FROM jobs WHERE asset=? AND input<>?""",
                        (face, source),
                    )
                    db.execute(
                        """INSERT INTO jobs(asset,photo,day,input,person,name,status) VALUES(?,?,?,?,?,?,'pending')
                        ON CONFLICT(asset) DO UPDATE SET person=excluded.person,name=excluded.name,day=excluded.day""",
                        (face, asset, day or "", source, person, name),
                    )
            db.execute("DELETE FROM jobs WHERE asset NOT IN (SELECT id FROM seen_face)")
            db.execute("DELETE FROM photos WHERE id NOT IN (SELECT id FROM seen_photo)")
            db.execute(
                "DELETE FROM rtx_life_stage_claims WHERE asset NOT IN (SELECT asset FROM jobs WHERE status<>'pending')"
            )
            db.execute(
                """UPDATE jobs SET status='withheld' WHERE status='complete' AND
                (json_extract(outcome,'$.stage')='unknown' OR json_extract(outcome,'$.action') IS NULL)"""
            )
            reuse_results(db, pilot)
            db.execute("DELETE FROM words")
            db.execute(
                """INSERT INTO words(photo,text,names)
                SELECT p.id,(SELECT group_concat(json_extract(value,'$.tag_data.text[0].val'),' ')
                FROM json_each(p.tags)),(SELECT group_concat(DISTINCT name) FROM jobs j WHERE j.photo=p.id)
                FROM photos p"""
            )
        (root / "inventory-updated").touch()
        print(json.dumps(status(db)))


def status(db):
    photos, tagged, regions, pending_ocr = db.execute(
        """SELECT count(*),sum(region_count>0),
        sum(region_count),sum(NOT ocr_done) FROM photos"""
    ).fetchone()
    return dict(
        photos=photos,
        ocr_photos=tagged,
        ocr_regions=regions,
        ocr_pending=pending_ocr,
        faces=dict(db.execute("SELECT status,count(*) FROM jobs GROUP BY status")),
        backends=dict(
            db.execute(
                """SELECT json_extract(outcome,'$.backend'),count(*) FROM jobs
                    WHERE status='complete' GROUP BY 1"""
            )
        ),
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", choices=("prepare", "status"))
    ap.add_argument("root", type=Path)
    ap.add_argument("--pilot", type=Path)
    args = ap.parse_args()
    os.umask(0o077)
    args.root.mkdir(parents=True, exist_ok=True)
    if args.mode == "prepare":
        if not args.pilot:
            ap.error("prepare requires --pilot")
        with (args.root / "worker.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            prepare(args.root, args.pilot.resolve())
    else:
        with closing(connect(args.root)) as conn:
            print(json.dumps(status(conn)))
