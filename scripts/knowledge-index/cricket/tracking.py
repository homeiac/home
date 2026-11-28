"""Carry bounded, timestamped player crops between adjacent sampled video windows."""

import base64
import io
import json

from PIL import Image

from .ledger import Ledger, finite


def reviewed_reference(
    ledger: Ledger, owner: str, album: str, asset: dict, prepared: dict, person: str
) -> dict | None:
    """Reuse an explicitly confirmed/corrected player box; outcome-only edits are not identity confirmation."""
    with ledger.connect() as db:
        rows = db.execute(
            "SELECT * FROM events WHERE owner=? AND album=? AND asset=? AND dismissed=0 ORDER BY rowid DESC",
            (owner, album, asset["id"]),
        ).fetchall()
        for raw in rows:
            row = dict(raw)
            overrides = json.loads(row["overrides"])
            if row["fingerprint"] != asset["fingerprint"] or not (
                row["review_state"] == "confirmed" or "actor" in overrides
            ):
                continue
            event = ledger._effective(db, row)
            if event["data"]["actor"] != person:
                continue
            where = event["evidence"].get("subject_location")
            if not where:
                continue
            for window in prepared["windows"]:
                if where["timestamp"] not in window.get("positions", []):
                    continue
                point = location(
                    {
                        "subject_location": {
                            **where,
                            "frame_index": window["positions"].index(
                                where["timestamp"]
                            ),
                        }
                    },
                    window,
                )
                if not point:
                    continue
                try:
                    image = crop(
                        window["frames"][point["frame_index"]],
                        point["person_box"] or point["face_box"],
                    )
                except (ValueError, OSError, IndexError):
                    continue
                return {
                    "asset": asset["id"],
                    "fingerprint": asset["fingerprint"],
                    "person": person,
                    "timestamp": point["timestamp"],
                    "basis": "user_confirmed",
                    "location": point,
                    "image": image,
                }
    return None


def box(value: object) -> list[float] | None:
    """Validate normalized x/y/width/height coordinates in a single source frame."""
    if (
        not isinstance(value, list)
        or len(value) != 4
        or not all(finite(v) for v in value)
    ):
        return None
    x, y, w, h = value
    if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > 1.000001 or y + h > 1.000001:
        return None
    return [round(float(v), 6) for v in value]


def location(raw: dict, window: dict) -> dict | None:
    """Tie coordinates to an actual supplied frame, never an invented timestamp."""
    value = raw.get("subject_location")
    if not isinstance(value, dict):
        return None
    index = value.get("frame_index")
    positions = window.get("positions", [])
    if (
        type(index) is not int
        or not 0 <= index < len(positions)
        or not finite(positions[index])
    ):
        return None
    person = box(value.get("person_box"))
    face = box(value.get("face_box"))
    if person is None and face is None:
        return None
    if face and person:
        cx, cy = face[0] + face[2] / 2, face[1] + face[3] / 2
        if (
            not person[0] <= cx <= person[0] + person[2]
            or not person[1] <= cy <= person[1] + person[3]
        ):
            return None
    return {
        "frame_index": index,
        "timestamp": positions[index],
        "person_box": person,
        "face_box": face,
    }


def can_match(raw: dict, window: dict, current: dict | None, role: str) -> bool:
    """A prior crop is a clue only with visible continuity and a fresh bounded match."""
    anchor = window.get("track_anchor")
    return bool(
        anchor
        and current
        and raw.get("track_match") is True
        and raw.get("scene_continuity") == "same_scene"
        and 0 <= current["timestamp"] - anchor["timestamp"] <= 40
        and (anchor["basis"] != "user_album_rule" or role == "batting")
    )


def crop(frame: str, coordinates: list[float]) -> str:
    """Keep a small same-video appearance reference without modifying original media."""
    with Image.open(io.BytesIO(base64.b64decode(frame, validate=True))) as source:
        x, y, w, h = coordinates
        left = max(0, int((x - w * 0.1) * source.width))
        top = max(0, int((y - h * 0.1) * source.height))
        right = min(source.width, int((x + w * 1.1) * source.width))
        bottom = min(source.height, int((y + h * 1.1) * source.height))
        if right - left < 2 or bottom - top < 2:
            raise ValueError("Player crop too small")
        selected = source.crop((left, top, right, bottom)).convert("RGB")
        selected.thumbnail((384, 384))
        out = io.BytesIO()
        selected.save(out, "JPEG", quality=85)
    return base64.b64encode(out.getvalue()).decode()


def advance(items: list[dict], asset: dict, window: dict, person: str) -> dict | None:
    """Refresh the anchor only where the target was observed; gaps/cuts never blindly propagate it."""
    if asset["kind"] != "video":
        return None
    candidates = [
        p
        for p in items
        if p["data"]["actor"] == person
        and p["evidence"].get("subject_location")
        and not p["evidence"].get("identity_excluded")
    ]
    for item in sorted(
        candidates,
        key=lambda p: p["evidence"]["subject_location"]["timestamp"],
        reverse=True,
    ):
        evidence = item["evidence"]
        where = evidence["subject_location"]
        basis = evidence["identity_basis"]
        if basis == "video_track_suggestion":
            basis = evidence["tracking"]["anchor_basis"]
        if basis not in {
            "visual_reference_suggestion",
            "user_album_rule",
            "user_confirmed",
            "immich_face_match",
        }:
            continue
        try:
            image = crop(
                window["frames"][where["frame_index"]],
                where["person_box"] or where["face_box"],
            )
        except (ValueError, OSError, IndexError):
            continue
        return {
            "asset": asset["id"],
            "fingerprint": asset["fingerprint"],
            "person": person,
            "timestamp": where["timestamp"],
            "basis": basis,
            "location": where,
            "image": image,
        }
    return None


def with_anchor(window: dict, anchor: dict | None, asset: dict) -> dict:
    """Fence anchors to the same source and nearby time; omit expired or cross-video identities."""
    result = dict(window)
    if (
        anchor
        and anchor["asset"] == asset["id"]
        and anchor["fingerprint"] == asset["fingerprint"]
        and window["start"] - anchor["timestamp"] <= 40
        and anchor["timestamp"] <= window["end"]
    ):
        result["track_anchor"] = {k: v for k, v in anchor.items() if k != "image"}
        result["track_image"] = anchor["image"]
    return result
