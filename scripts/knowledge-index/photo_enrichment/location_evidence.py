"""Resolve photo-detail place facts using local, source-attributed evidence."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from .places import coordinates


def immich_label(place: dict) -> str:
    """Format an administrative place at the finest recorded level."""
    return ", ".join(dict.fromkeys(place[key].strip() for key in ("city", "state", "country")
                                   if isinstance(place.get(key), str) and place[key].strip()))


def photo_place(photo: dict, snapshot: Path) -> dict:
    """Preserve competing user annotations and distinguish coordinates from a named place."""
    choices = {}
    for group in photo["groups"]:
        venue = (group.get("venue") or "").strip()
        location = (group.get("location") or "").strip()
        label = ", ".join(dict.fromkeys(value for value in (venue, location) if value))
        if label:
            choices.setdefault(label, []).append(group["id"])
    if choices:
        return dict(source="user", precision="user annotation", labels=sorted(choices),
                    group_ids={label: sorted(ids) for label, ids in choices.items()},
                    status="multiple" if len(choices) > 1 else "known")
    unavailable = False
    if snapshot.is_file():
        try:
            with closing(sqlite3.connect(snapshot.as_uri() + "?mode=ro&immutable=1", uri=True)) as db:
                row = db.execute("SELECT json_extract(metadata,'$.place') FROM context WHERE path=? AND size=?",
                                 (photo["path"], photo["size_bytes"])).fetchone()
            if row and row[0]:
                place = json.loads(row[0])
                if not isinstance(place, dict):
                    raise ValueError("Invalid Immich place")
                label = immich_label(place)
                if label:
                    level = next(k for k in ("city", "state", "country")
                                 if isinstance(place.get(k), str) and place[k].strip())
                    return dict(source="immich", precision=level, labels=[label], status="known")
        except (sqlite3.Error, ValueError):
            unavailable = True
    try:
        coordinates(photo.get("latitude"), photo.get("longitude"))
    except (ValueError, TypeError):
        return dict(source=None, precision=None, labels=[], status="unavailable" if unavailable else "unknown")
    return dict(source=photo.get("gps_source"), precision="coordinates", labels=[],
                status="coordinates", place_lookup_unavailable=unavailable)
