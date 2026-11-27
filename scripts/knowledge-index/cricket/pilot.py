"""Select a reproducible duration-stratified pilot with cached reaction and bowling examples."""

import argparse
import json
import logging
from pathlib import Path

from .context import role_hint
from .ledger import Ledger
from .prepare import save_private
from .reactions import outcome


def main() -> None:
    """Select at most 36 videos plus eight photos, without mutating analysis state."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    ledger = Ledger(args.ledger)
    runtime = json.loads(args.runtime.read_text())
    with ledger.connect() as db:
        videos = [
            r[0]
            for r in db.execute(
                "SELECT id FROM assets WHERE kind='video' ORDER BY duration,id"
            )
        ]
        photos = [
            r[0]
            for r in db.execute("SELECT id FROM assets WHERE kind='photo' ORDER BY id")
        ]
    selected = (
        {videos[round(i * (len(videos) - 1) / 31)] for i in range(min(32, len(videos)))}
        if videos
        else set()
    )
    extras = []
    for asset in videos:
        audio = runtime["audio"].get(asset, {})
        if role_hint(audio.get("visual_summary") or "") == "bowling" or any(
            outcome(s["text"]) for s in json.loads(audio.get("transcript") or "[]")
        ):
            extras.append(asset)
    selected.update(extras[:4])
    video_count = len(selected)
    if photos:
        selected.update(
            photos[round(i * (len(photos) - 1) / 7)] for i in range(min(8, len(photos)))
        )
    save_private(args.output, sorted(selected))
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger(__name__).info(
        "Pilot: %s videos and %s photos", video_count, len(selected) - video_count
    )


if __name__ == "__main__":
    main()
