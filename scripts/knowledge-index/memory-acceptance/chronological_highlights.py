"""Select dated highlights from a private, person-specific candidate inventory."""
import argparse
import hashlib
import json
from datetime import date
from pathlib import Path


def select_highlights(rows: list[dict]) -> list[dict]:
    """Choose one mapped original per quarter, independently of input order."""
    quarters = {}
    seen = set()
    for row in rows:
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
    args = parser.parse_args()
    print(json.dumps([r["id"] for r in select_highlights(json.loads(args.inventory.read_text()))]))
