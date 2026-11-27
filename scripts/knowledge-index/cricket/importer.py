"""Import a frozen album inventory without changing source media or reviewed events."""

import argparse
import json
import logging
import math
import os
import tempfile
from pathlib import Path

from .ledger import Ledger


def select_album(inventory: list, name: str) -> dict:
    """Resolve a single explicitly named, owned album."""
    candidates = [a for a in inventory if a["name"] == name]
    if len(candidates) != 1 or not candidates[0].get("ownerMatches"):
        raise ValueError("Expected one owned album with this name")
    return candidates[0]


def select_person(people: list, name: str) -> str:
    """Resolve an exact or unique first-name match; never guess among people."""
    exact = [p for p in people if p["name"].casefold() == name.casefold()]
    matches = exact or [
        p for p in people if p["name"].split()[0].casefold() == name.casefold()
    ]
    if len(matches) != 1:
        raise ValueError("Person name is ambiguous or absent")
    return matches[0]["id"]


def import_album(
    ledger: Ledger | None,
    album: dict,
    sources: dict,
    default_batter: str,
    limit: int = 0,
) -> dict:
    """Queue unique eligible originals; dry runs do not create or open a ledger."""
    owner, aid = album["owner"], album["id"]
    assets = album["assets"]
    if len({a["id"] for a in assets}) != len(assets):
        raise ValueError("Duplicate inventory asset")
    counts = {
        "photos": 0,
        "videos": 0,
        "unavailable": 0,
        "out_of_scope": 0,
        "invalid_duration": 0,
    }
    if ledger:
        ledger.add_album(owner, aid, default_batter)
    for asset in assets[: limit or None]:
        key = asset["id"]
        source = sources.get(key)
        if asset.get("isOffline") or asset.get("isTrashed") or not source:
            counts["unavailable"] += 1
            continue
        if asset.get("ownerId") != owner or asset["type"] not in {"IMAGE", "VIDEO"}:
            counts["out_of_scope"] += 1
            continue
        if source["size"] != asset["exifInfo"]["fileSizeInByte"]:
            raise ValueError("Original size changed after inventory")
        video = asset["type"] == "VIDEO"
        # Immich v3 exposes asset durations in milliseconds.
        duration = asset["duration"] / 1000 if video else None
        if video and (not math.isfinite(duration) or duration <= 0):
            counts["invalid_duration"] += 1
            continue
        if ledger:
            ledger.add_asset(
                owner,
                aid,
                key,
                "video" if video else "photo",
                duration,
                source["fingerprint"],
                source["locator"],
            )
            with ledger.connect(True) as db:
                db.execute(
                    "INSERT OR IGNORE INTO jobs(owner,asset,version,stage) VALUES(?,?,?,?)",
                    (owner, key, "cricket-v1", "analyze"),
                )
        counts["videos" if video else "photos"] += 1
    return counts


def role_event(
    role: str,
    *,
    duration: float | None,
    default_batter: str,
    featured_batter: bool = False,
    identified_actor: str | None = None,
    confirmed_people: set[str] | None = None,
) -> dict:
    """Separate observed activity, the album assumption, and independent identity evidence."""
    if role not in {"batting", "bowling", "other", "unknown"}:
        raise ValueError("Unknown role")
    actor = (
        identified_actor if identified_actor in (confirmed_people or set()) else None
    )
    if role == "batting" and featured_batter and actor is None:
        actor = default_batter
    return {
        "actor": actor,
        "role": role,
        "outcome": "unknown",
        "wicket_credit": "unknown",
        "start": 0 if duration else None,
        "end": duration,
        "delivery_start": None,
        "outcome_end": None,
    }


def main() -> None:
    """Import an album and its private display names or report a dry run."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--people", type=Path, required=True)
    parser.add_argument("--album-name", default="All cricket videos")
    parser.add_argument("--person-name", default="Adil")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.limit < 0:
        parser.error("Limit must not be negative")
    album = select_album(json.loads(args.inventory.read_text()), args.album_name)
    actor = select_person(album["people"], args.person_name)
    source = json.loads(args.runtime.read_text())
    ledger = None if args.dry_run else Ledger(args.ledger)
    counts = import_album(ledger, album, source["sources"], actor, args.limit)
    if not args.dry_run:
        args.people.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", dir=args.people.parent, delete=False
        ) as output:
            json.dump({p["id"]: p["name"] for p in album["people"]}, output)
            temporary = Path(output.name)
        os.replace(temporary, args.people)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger(__name__).info(
        "%s", json.dumps({"dry_run": args.dry_run, **counts})
    )


if __name__ == "__main__":
    main()
