"""Keep native Immich face instances distinct, even before a person is recognized."""

import json
from pathlib import Path
from uuid import UUID

from .tracking import box


def identifier(value: str) -> str:
    """Accept only real, nonzero UUIDs returned by Immich; never invent an ID."""
    parsed = UUID(value)
    if not parsed.int:
        raise ValueError("Empty Immich identifier")
    return str(parsed)


def normalize(faces: list[dict]) -> list[dict]:
    """Retain every returned face, including faces with no person or name."""
    result, seen = [], set()
    for face in faces:
        face_id = identifier(face["id"])
        if face_id in seen:
            raise ValueError("Duplicate native face ID in a frame")
        seen.add(face_id)
        width, height = face["imageWidth"], face["imageHeight"]
        coords = box(
            [
                face["boundingBoxX1"] / width,
                face["boundingBoxY1"] / height,
                (face["boundingBoxX2"] - face["boundingBoxX1"]) / width,
                (face["boundingBoxY2"] - face["boundingBoxY1"]) / height,
            ]
        )
        if coords is None:
            raise ValueError("Invalid native face coordinates")
        person = face.get("person") or {}
        result.append(
            {
                "face_id": face_id,
                "person_id": identifier(person["id"]) if person.get("id") else None,
                "name": (person.get("name") or "").strip() or None,
                "face_box": coords,
            }
        )
    return result


def load(folder: Path, asset: dict) -> dict:
    """Reject another owner/source's registry rather than silently carrying identities."""
    path = folder / "faces" / (asset["id"] + ".json")
    if not path.exists():
        return {}
    value = json.loads(path.read_text())
    if (
        any(value.get(k) != asset[k] for k in ("owner", "fingerprint"))
        or value.get("asset") != asset["id"]
    ):
        raise ValueError("Face registry source changed")
    return value


def for_window(registry: dict, window: dict) -> list[dict]:
    """Attach all detections at actual sampled timestamps, not just named faces."""
    positions = window.get("positions", [])
    return [
        {**frame, "frame_index": positions.index(frame["timestamp"])}
        for frame in registry.get("frames", [])
        if frame["timestamp"] in positions
    ]


def subject(where: dict | None, frames: list[dict]) -> dict | None:
    """Associate a player with one unambiguous native face inside the supplied box."""
    if not where:
        return None
    region = where.get("face_box") or where.get("person_box")
    if not region:
        return None
    x, y, w, h = region
    candidates = []
    for frame in frames:
        if frame["timestamp"] != where["timestamp"]:
            continue
        for face in frame["faces"]:
            fx, fy, fw, fh = face["face_box"]
            overlap = max(0, min(x + w, fx + fw) - max(x, fx)) * max(
                0, min(y + h, fy + fh) - max(y, fy)
            )
            if overlap / (fw * fh) >= 0.8:
                candidates.append(
                    {
                        **face,
                        "frame_asset": frame["frame_asset"],
                        "timestamp": frame["timestamp"],
                    }
                )
    return candidates[0] if len(candidates) == 1 else None
