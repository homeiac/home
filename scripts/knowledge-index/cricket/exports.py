"""Export a corrected interval on demand, leaving original media and older revisions untouched."""

import hashlib
import os
import subprocess
import tempfile
import threading
from pathlib import Path

from .ledger import Conflict, encoded
from .prepare import save_private

SLOTS = threading.BoundedSemaphore(2)


def target(event: dict, folder: Path) -> Path:
    """Changing source version or effective revision creates a different derived file."""
    key = hashlib.sha256(
        encoded(
            {
                "event": event["id"],
                "revision": event["revision"],
                "fingerprint": event["fingerprint"],
                "start": event["data"]["start"],
                "end": event["data"]["end"],
            }
        ).encode()
    ).hexdigest()
    return folder / (key + ".mp4")


def create(event: dict, source: Path, folder: Path) -> Path:
    """Accurately trim/re-encode audio and video with two low-priority single-thread slots."""
    data = event["data"]
    if data["start"] is None or data["end"] is None:
        raise ValueError("Clip export requires a video highlight")
    output = target(event, folder)
    if output.is_file():
        return output
    if not SLOTS.acquire(blocking=False):
        raise Conflict("Two clips are already exporting; retry shortly")
    temporary = None
    try:
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.NamedTemporaryFile(
            dir=folder, suffix=".mp4", delete=False
        ) as handle:
            temporary = Path(handle.name)
        command = [
            "nice",
            "-n",
            "15",
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-threads",
            "1",
            "-ss",
            str(data["start"]),
            "-i",
            str(source),
            "-t",
            str(data["end"] - data["start"]),
            "-map",
            "0:V:0",
            "-map",
            "0:a:0?",
            "-vf",
            "scale=w='min(1280,iw)':h='min(1280,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "20",
            "-threads",
            "1",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(temporary),
        ]
        try:
            subprocess.run(command, capture_output=True, timeout=600, check=True)
        except subprocess.SubprocessError as error:
            raise ValueError(
                "Clip export failed; the original and correction remain saved"
            ) from error
        if temporary.stat().st_size < 100:
            raise ValueError("Clip export was empty")
        os.replace(temporary, output)
        save_private(
            output.with_suffix(".json"),
            {
                "event": event["id"],
                "revision": event["revision"],
                "asset": event["asset"],
                "fingerprint": event["fingerprint"],
                "start": data["start"],
                "end": data["end"],
                "format": "mp4-h264-aac-1280",
            },
        )
        return output
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        SLOTS.release()
