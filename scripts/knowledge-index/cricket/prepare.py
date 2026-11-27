"""Cache host-decoded cricket previews locally while preserving completed evidence."""

import argparse
import base64
import json
import logging
import os
import shlex
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .evidence import VERSION, audio_evidence, fingerprint
from .ledger import Ledger


def save_private(path: Path, value: dict) -> None:
    """Atomically save private JSON with restrictive file permissions."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as output:
        json.dump(value, output)
        temporary = Path(output.name)
    os.replace(temporary, path)


def save_preview(folder: Path, asset: dict, prepared: dict) -> None:
    """Supply browser-readable previews for HEIC and other original photo formats."""
    if asset["kind"] != "photo":
        return
    target = folder / (asset["id"] + ".jpg")
    with tempfile.NamedTemporaryFile(dir=folder, delete=False) as output:
        output.write(
            base64.b64decode(prepared["windows"][0]["frames"][0], validate=True)
        )
        temporary = Path(output.name)
    os.replace(temporary, target)


def prepare(asset: dict, *, host: str, folder: Path, audio: dict | None) -> dict:
    """Reuse an exact preparation or extract it through an inventory-approved host."""
    key = fingerprint({"asset": asset, "audio": audio})
    target = folder / (asset["id"] + ".json")
    if target.exists():
        old = json.loads(target.read_text())
        if old.get("cache_key") == key and old.get("version") == VERSION:
            save_preview(folder, asset, old)
            return {
                "asset": asset["id"],
                "state": "reused",
                "windows": len(old["windows"]),
            }
    packet = {**asset, "library": "/local-3TB-backup/gphotos/library"}
    source = Path(__file__).with_name("evidence.py").read_text()
    started = time.monotonic()
    response = subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=10",
            host,
            "python3 -c " + shlex.quote(source),
        ],
        input=json.dumps(packet),
        text=True,
        capture_output=True,
        timeout=1800,
        check=False,
    )
    if response.returncode:
        raise RuntimeError(
            "Source extraction failed; private source identity retained for retry"
        )
    result = json.loads(response.stdout)
    for window in result["windows"]:
        window["audio"] = audio_evidence(audio, window["start"], window["end"])
    result.update(asset=asset["id"], cache_key=key, seconds=time.monotonic() - started)
    save_private(target, result)
    save_preview(folder, asset, result)
    return {
        "asset": asset["id"],
        "state": "prepared",
        "windows": len(result["windows"]),
    }


def main() -> None:
    """Prepare a bounded set without writing suggestions or changing production workers."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--folder", type=Path, required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--limit", type=int, default=32)
    parser.add_argument("--workers", type=int, choices=range(1, 9), required=True)
    parser.add_argument("--kind", choices=["video", "photo"], default="video")
    args = parser.parse_args()
    ledger = Ledger(args.ledger)
    runtime = json.loads(args.runtime.read_text())
    with ledger.connect() as db:
        # Stable duration strata include both brief and long clips in the pilot.
        assets = [
            dict(row)
            for row in db.execute(
                "SELECT * FROM assets WHERE kind=? ORDER BY duration,id", (args.kind,)
            )
        ]
    if 0 < args.limit < len(assets):
        assets = [
            assets[round(i * (len(assets) - 1) / max(1, args.limit - 1))]
            for i in range(args.limit)
        ]

    def run(asset: dict) -> dict:
        try:
            return prepare(
                asset,
                host=args.host,
                folder=args.folder,
                audio=runtime["audio"].get(asset["id"]),
            )
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            return {"state": "error", "error": type(error).__name__}

    started = time.monotonic()
    with ThreadPoolExecutor(args.workers) as pool:
        results = list(pool.map(run, assets))
    summary = {
        state: sum(row["state"] == state for row in results)
        for state in ("prepared", "reused", "error")
    }
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger(__name__).info(
        "%s", json.dumps({**summary, "seconds": round(time.monotonic() - started, 2)})
    )
    if summary["error"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
