"""Serve an isolated synthetic cricket fixture for browser verification."""

import argparse
import json
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace

from cricket.api import CricketAPI
from cricket.ledger import Ledger
from photo_enrichment.server import make_server


def main() -> None:
    """Create a tiny playable original and announce the loopback port in a file."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True, type=Path)
    args = parser.parse_args()
    args.state.mkdir(parents=True, exist_ok=True)
    video = args.state / "fixture.mp4"
    if not video.exists():
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "testsrc2=size=256x144:rate=12",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440",
                "-t",
                "8",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                str(video),
            ],
            check=True,
        )
    ledger = Ledger(args.state / "ledger.sqlite3")
    ledger.add_album("fixture-owner", "fixture-album", "person-a")
    ledger.add_asset(
        "fixture-owner", "fixture-album", "video", "video", 8, "fixture-v1", video.name
    )
    if not ledger.list_events("fixture-owner", "fixture-album", True):
        ledger.create_event(
            "fixture-owner",
            "fixture-album",
            "video",
            {
                "actor": "person-a",
                "role": "batting",
                "outcome": "four",
                "wicket_credit": "unknown",
                "start": 1,
                "end": 6,
                "delivery_start": 2,
                "outcome_end": 5,
            },
        )
    api = CricketAPI(
        ledger,
        "fixture-owner",
        args.state,
        {"person-a": "Test batter", "person-b": "Other player"},
    )
    server = make_server(
        SimpleNamespace(lock=threading.RLock()), args.state, "127.0.0.1", 0, cricket=api
    )
    (args.state / "ready.json").write_text(
        json.dumps({"url": f"http://127.0.0.1:{server.server_port}/cricket"})
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
