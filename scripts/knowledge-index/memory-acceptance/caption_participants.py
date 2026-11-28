"""Ground reviewed caption phrases in per-asset Immich detections, independent of the album."""

import hashlib
import json
import re
from datetime import date

from openlabel_album import bind_face, stable_id, text_value

# Discovery cues only. A text match or an extra face is never proof of a role.
PEOPLE = re.compile(
    r"\b(?:(?:an?|the|another|other|both|some|two|several|his|her|their|my|our)\s+)?"
    r"(?:(?:older|younger|smaller|adult|young|little)\s+)?"
    r"(?:group of (?:friends|people|children)|group photo|family members|"
    r"people|person|adults?|women|woman|men|man|children|child|infants?|babies|baby|"
    r"someone|somebody|group|friends?|family|mother|father|sister|brother|siblings?|"
    r"parents?|boys?|girls?|colleagues?|coworkers?|classmates?|couple|partner|hand(?= reaches))\b",
    re.I,
)
PLURAL = re.compile(
    r"\b(?:people|adults|women|men|children|infants|babies|group|family|friends|"
    r"siblings|parents|boys|girls|colleagues|coworkers|classmates|couple)\b",
    re.I,
)


def candidate_phrases(captions: list[str]) -> list[str]:
    """Find common person references for visual checking. Repeated phrases need review."""
    phrases = dict.fromkeys(m.group() for c in captions for m in PEOPLE.finditer(c))
    return [phrase for phrase in phrases if sum(c.count(phrase) for c in captions) == 1]


BANDS = {
    "baby_toddler": (0, 3),
    "preschool": (2, 6),
    "school_age": (5, 13),
    "teen": (12, 20),
    "young_adult": (17, 35),
    "adult": (18, 130),
}


def age_status(row: dict, birth_year: int) -> str:
    """Check visual evidence using the possible ages on a date with only a known birth year."""
    if row.get("composite"):
        return "composite"
    owner = row.get("owner") or {}
    if row["date"] in (
        owner.get("confirmed_capture_date"),
        owner.get("confirmed_file_date"),
    ):
        if owner.get("confirmed_capture_date") or owner.get("age") is not None:
            return "confirmed"
    result = row.get("accepted") or {}
    if (
        row.get("local_skip")
        or row["status"] == "unresolved"
        or result.get("confidence") not in {"medium", "high"}
    ):
        return "unresolved"
    if row["status"] == "conflict":
        return "conflict"
    primary = BANDS.get(result.get("stage"))
    if not primary:
        return "unresolved"
    oldest = date.fromisoformat(row["date"]).year - birth_year
    youngest = max(0, oldest - 1)
    bands = [primary]
    if alt := BANDS.get(result.get("alternate")):
        bands.append(alt)
    return (
        "compatible"
        if any(youngest <= hi and oldest >= lo for lo, hi in bands)
        else "conflict"
    )


def fingerprint(captions: list[str]) -> str:
    return hashlib.sha256(
        json.dumps(sorted(captions), ensure_ascii=False).encode()
    ).hexdigest()


def attach(
    scene: dict, asset: str, captions: list[str], regions: dict, decision: dict
) -> None:
    """Validate reviewed phrases and bind them to current source detections before persistence."""
    if decision["caption_hash"] != fingerprint(captions):
        raise ValueError("Caption changed since participant review")
    data = scene["openlabel"]
    width, height = (data["metadata"]["image_" + axis] for axis in ("width", "height"))
    for mention in decision["mentions"]:
        phrase = mention["words"]
        if not phrase or sum(c.count(phrase) for c in captions) != 1:
            raise ValueError("Mention requires an unambiguous source phrase")
        key = stable_id(asset, "mention", phrase)
        contexts = data.setdefault("contexts", {})
        if key in contexts:
            raise ValueError("Duplicate caption mention")
        refs = []
        for source in mention["faces"]:
            if source["namespace"] != "immich":
                raise ValueError("Participant requires a native Immich face ID")
            region = regions[source["namespace"], source["face_id"]]
            if source["box"] != region["box"] or (
                source["person_id"] and region["person_id"] != source["person_id"]
            ):
                raise ValueError("Face geometry or reviewed identity changed")
            # A previously unclustered detection may acquire a person ID later.
            ref = dict(source, person_id=region["person_id"])
            refs.append(
                {
                    "type": "object",
                    "uid": bind_face(
                        asset,
                        data.setdefault("objects", {}),
                        regions,
                        width,
                        height,
                        ref,
                    ),
                }
            )
        if len(refs) != len({r["uid"] for r in refs}) or not (
            refs or mention.get("reason")
        ):
            raise ValueError(
                "Expected distinct face occurrences or a withholding reason"
            )
        meta = [
            text_value("words", phrase),
            text_value("reason", mention.get("reason", "")),
        ]
        contexts[key] = {
            "name": phrase,
            "type": "caption_mention",
            "context_data": {"text": meta},
        }
        if not refs:
            continue
        relations = data.setdefault("relations", {})
        relations[stable_id(key, "refers_to")] = {
            "type": "refers_to",
            "name": "caption reference",
            "rdf_subjects": [{"type": "context", "uid": key}],
            "rdf_objects": refs,
        }
        for name, role in mention.get("actions", []):
            (uid,) = [
                uid for uid, a in data.get("actions", {}).items() if a["name"] == name
            ]
            relations[stable_id(key, uid, role)] = {
                "type": role,
                "name": "caption participant",
                "rdf_subjects": [{"type": "action", "uid": uid}],
                "rdf_objects": refs,
            }
