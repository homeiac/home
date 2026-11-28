"""Adapt cricket checkpoints to the life-stage OpenLABEL contract and revision writer.

The SQLite event ledger and upload registry are import sources. The shared
openlabel_album module owns schema validation, face binding, and PostgreSQL
revision persistence. No alternative annotation table or native face ID is made.
"""

import argparse
import base64
import importlib
import io
import json
import logging
import sys
from pathlib import Path
from types import ModuleType

from PIL import Image

from .face_context import load, subject
from .immich_frames import frame_key
from .ledger import Ledger
from .prepare import save_private
from .vocabulary import ACTIONS, OUTCOMES, VERSION

PRODUCER = "cricket-openlabel-v1"


def shared_module(folder: Path) -> ModuleType:
    """Load the existing life-stage implementation, not a copy of its binder/writer."""
    folder = folder.resolve()
    if not (folder / "openlabel_album.py").is_file():
        raise FileNotFoundError("Shared life-stage OpenLABEL module is required")
    sys.path.insert(0, str(folder))
    module = importlib.import_module("openlabel_album")
    if Path(module.__file__).resolve().parent != folder:
        raise ValueError("Different OpenLABEL module already loaded")
    return module


def registry_for_scene(folder: Path, asset: dict) -> dict:
    """Recover legacy frame dimensions only from checksum-matched local evidence.

    This read-only adaptation neither uploads frames nor changes checkpoints.
    """
    registry = load(folder, asset)
    missing = [
        f
        for f in registry.get("frames", [])
        if "image_width" not in f or "image_height" not in f
    ]
    if missing:
        prepared = json.loads((folder / (asset["id"] + ".json")).read_text())
        images = {
            stamp: image
            for window in prepared["windows"]
            for stamp, image in zip(window["positions"], window["frames"], strict=True)
        }
        for frame in missing:
            image = images[frame["timestamp"]]
            if frame_key(asset, frame["timestamp"], image) != frame["key"]:
                raise ValueError(
                    "Legacy dimensions require the exact uploaded evidence"
                )
            with Image.open(
                io.BytesIO(base64.b64decode(image, validate=True))
            ) as source:
                frame["image_width"], frame["image_height"] = source.size
    return registry


def scene(shared: ModuleType, asset: dict, registry: dict, events: list[dict]) -> dict:
    """Bind every native detection, then attach effective cricket facts and provenance."""
    if registry and (
        registry["owner"] != asset["owner"]
        or registry["asset"] != asset["id"]
        or registry["fingerprint"] != asset["fingerprint"]
    ):
        raise ValueError("Native face registry scope changed")
    stable, text = shared.stable_id, shared.text_value
    data = {
        "metadata": {
            "schema_version": "1.0.0",
            "vocabulary_release": VERSION,
            "producer": PRODUCER,
            "source_asset": asset["id"],
            "source_fingerprint": asset["fingerprint"],
            "owner": asset["owner"],
            "coordinate_convention": "oriented evidence-frame pixels; bbox center-x,center-y,width,height",
            "frame_index_basis": "ordered sampled frames; source seconds in frame_properties.timestamp",
            "native_detection_complete": registry.get("detection_complete", False),
        },
        "objects": {},
        "actions": {},
        "events": {},
        "contexts": {},
        "relations": {},
        "frames": {},
    }
    seen = set()
    for index, frame in enumerate(
        sorted(registry.get("frames", []), key=lambda f: f["timestamp"] or 0)
    ):
        width, height = frame["image_width"], frame["image_height"]
        if width <= 0 or height <= 0:
            raise ValueError("Oriented frame dimensions required")
        dynamic = {
            "frame_properties": {
                "timestamp": float(frame["timestamp"] or 0),
                "source_asset": asset["id"],
                "immich_frame_asset": frame["frame_asset"],
                "image_width": width,
                "image_height": height,
                "detection_state": frame["state"],
            },
            "objects": {},
        }
        data["frames"][str(index)] = dynamic
        for face in frame["faces"]:
            fid = face["face_id"]
            if fid in seen:
                raise ValueError("Native face instance repeated across frame assets")
            seen.add(fid)
            x, y, w, h = face["face_box"]
            ref = {
                "namespace": "immich",
                "face_id": fid,
                "person_id": face["person_id"],
            }
            regions = {("immich", fid): {**ref, "box": [x, y, x + w, y + h]}}
            uid = shared.bind_face(
                asset["id"], data["objects"], regions, width, height, ref
            )
            obj = data["objects"][uid]
            obj["frame_intervals"] = [{"frame_start": index, "frame_end": index}]
            dynamic["objects"][uid] = {
                "object_data": {"bbox": obj["object_data"].pop("bbox")}
            }
            obj["object_data"]["text"].extend(
                [
                    text("immich_frame_asset", frame["frame_asset"]),
                    text(
                        "action_withheld",
                        "No face-grounded cricket action has been established for this detection.",
                    ),
                ]
            )
    age = registry.get("identity_context", {})
    if age:
        data["contexts"][stable(asset["id"], "cricket age context")] = {
            "name": "Age at recording",
            "type": "capture_age_context",
            "context_data": {
                "text": [
                    text(k, str(v)) for k, v in sorted(age.items()) if v is not None
                ]
            },
        }
    for event in events:
        if (
            event["asset"] != asset["id"]
            or event["owner"] != asset["owner"]
            or event["fingerprint"] != asset["fingerprint"]
        ):
            raise ValueError("Cricket event source changed")
        if event["dismissed"] or event["review_state"] == "superseded":
            continue
        effective, evidence = event["data"], event["evidence"]
        uid = stable(asset["id"], "cricket action", event["id"])
        fields = [
            text("event_id", event["id"]),
            text("review_state", event["review_state"]),
            text("identity_basis", evidence.get("identity_basis", "unresolved")),
            text("person_id", effective["actor"] or ""),
            text("source_evidence", json.dumps(evidence, sort_keys=True)),
            text(
                "human_overrides",
                json.dumps(event.get("overrides", {}), sort_keys=True),
            ),
        ]
        numbers = [{"name": "event_revision", "val": event["revision"]}] + [
            {"name": k + "_seconds", "val": effective[k]}
            for k in ("start", "end", "delivery_start", "outcome_end")
            if effective[k] is not None
        ]
        data["actions"][uid] = {
            "name": effective["role"],
            "type": ACTIONS[effective["role"]][0],
            "action_data": {"text": fields, "num": numbers},
        }
        outcome_uid = stable(asset["id"], "cricket outcome", event["id"])
        data["events"][outcome_uid] = {
            "name": effective["outcome"],
            "type": OUTCOMES[effective["outcome"]][0],
            "event_data": {
                "text": [
                    text("review_state", event["review_state"]),
                    text("wicket_credit", effective["wicket_credit"]),
                ],
                "num": numbers,
            },
        }
        data["relations"][stable(uid, "outcome")] = {
            "name": "outcome",
            "type": "outcome",
            "rdf_subjects": [{"type": "action", "uid": uid}],
            "rdf_objects": [{"type": "event", "uid": outcome_uid}],
        }
        native = subject(evidence.get("subject_location"), registry.get("frames", []))
        # A changed person link invalidates an old identity binding. An album-level
        # batting assumption without a localized face never creates an actor link.
        compatible = native and (
            not effective["actor"]
            or not native["person_id"]
            or effective["actor"] == native["person_id"]
        )
        if compatible:
            face_uid = stable(asset["id"], "immich", native["face_id"])
            data["relations"][stable(uid, "actor", face_uid)] = {
                "name": "actor",
                "type": "actor",
                "rdf_subjects": [{"type": "action", "uid": uid}],
                "rdf_objects": [{"type": "object", "uid": face_uid}],
            }
            obj = data["objects"][face_uid]["object_data"]
            obj["text"] = [v for v in obj["text"] if v["name"] != "action_withheld"]
        else:
            fields.append(
                text(
                    "actor_binding_withheld",
                    "No current unambiguous native face binding; retain the editable person assertion separately.",
                )
            )
    return {"openlabel": data}


def publish(
    connection: object, shared: ModuleType, album: str, scenes: dict, schema: Path
) -> dict:
    """Use the existing atomic revision writer and avoid replacing another producer's scenes."""
    shared.validate_scenes(scenes, schema)
    with connection.transaction():
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (album,)
        )
        exists = connection.execute(
            "SELECT to_regclass('openlabel_album_scene')"
        ).fetchone()[0]
        if exists:
            for asset in scenes:
                prior = connection.execute(
                    "SELECT scene FROM openlabel_album_scene WHERE album=%s AND asset=%s ORDER BY revision DESC LIMIT 1",
                    (album, asset),
                ).fetchone()
                if (
                    prior
                    and prior[0]["openlabel"]["metadata"].get("producer") != PRODUCER
                ):
                    raise ValueError(
                        "Existing scene belongs to another producer; merge explicitly"
                    )
        return shared.persist(connection, album, scenes)


def main() -> None:
    """Validate private scenes; publish only through the shared PostgreSQL writer."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--shared-module", type=Path, required=True)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Use the existing libpq environment and shared scene table",
    )
    args = parser.parse_args()
    shared = shared_module(args.shared_module)
    ledger = Ledger(args.ledger, read_only=True)
    with ledger.connect() as db:
        albums = [dict(r) for r in db.execute("SELECT * FROM albums")]
        if len(albums) != 1:
            raise ValueError("One explicitly scoped album required")
        album = albums[0]
        assets = [
            dict(r)
            for r in db.execute(
                "SELECT a.* FROM assets a JOIN members m ON a.owner=m.owner AND a.id=m.asset "
                "WHERE m.owner=? AND m.album=? ORDER BY a.id",
                (album["owner"], album["id"]),
            )
        ]
    events = ledger.list_events(album["owner"], album["id"], True)
    scenes = {}
    for asset in assets:
        if asset["owner"] != album["owner"]:
            raise ValueError("Mixed owner import refused")
        registry = registry_for_scene(args.evidence, asset)
        if registry:
            scenes[asset["id"]] = scene(
                shared,
                asset,
                registry,
                [e for e in events if e["asset"] == asset["id"]],
            )
    shared.validate_scenes(scenes, args.schema)
    if args.publish:
        import psycopg

        with psycopg.connect(autocommit=True) as connection:
            scenes = publish(connection, shared, album["id"], scenes, args.schema)
    save_private(
        args.output, {"album": album["id"], "owner": album["owner"], "scenes": scenes}
    )
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger(__name__).info(
        "Validated %s OpenLABEL scenes; PostgreSQL publication=%s",
        len(scenes),
        args.publish,
    )


if __name__ == "__main__":
    main()
