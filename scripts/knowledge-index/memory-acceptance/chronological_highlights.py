"""Select dated highlights from a private, person-specific candidate inventory."""
import argparse
import hashlib
import json
from datetime import date
from pathlib import Path


def select_highlights(rows: list[dict], media_types: dict | None = None) -> list[dict]:
    """Choose one mapped original per quarter, independently of input order."""
    quarters = {}
    seen = set()
    for row in rows:
        kind = (media_types or {}).get(row["id"], {}).get("type", row.get("media_type"))
        if kind == "Collage":
            continue
        if row.get("reason") or not row.get("date") or not (row["local"] or row["native"]):
            continue
        asset = row["id"]
        if not asset or asset in seen:
            raise ValueError("Expected one record per mapped original")
        seen.add(asset)
        captured = date.fromisoformat(row["date"])
        quarter = (captured.year, (captured.month - 1) // 3)
        rank = (not (row["local"] and row["native"]), not row["caption"],
                hashlib.sha256(asset.encode()).digest())
        if quarter not in quarters or rank < quarters[quarter][0]:
            quarters[quarter] = (rank, row)
    return [quarters[key][1] for key in sorted(quarters)]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path, help="Private JSON candidate inventory")
    parser.add_argument("--media-types", type=Path, help="Private per-asset media classification")
    args = parser.parse_args()
    classification = args.media_types or args.inventory.parent / "album-life-stage-pilot/composite-types.json"
    media_types = json.loads(classification.read_text()) if classification.is_file() else None
    if args.media_types and media_types is None:
        parser.error("Media classification file is missing")
    selected = select_highlights(json.loads(args.inventory.read_text()), media_types)
    print(json.dumps([row["id"] for row in selected]))
