"""Bounded frame windows and source-relative transcript evidence; originals are read-only."""

import argparse
import base64
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

VERSION = "cricket-evidence-v1"


def windows(
    duration: float, width: float = 30, overlap: float = 10
) -> list[tuple[float, float]]:
    """Cover the whole video with overlap so deliveries on a boundary remain visible."""
    if not math.isfinite(duration) or duration <= 0 or not 0 <= overlap < width:
        raise ValueError("Invalid video window geometry")
    result = []
    start = 0.0
    while start < duration:
        end = min(duration, start + width)
        result.append((start, end))
        if end == duration:
            break
        start = end - overlap
    return result


def positions(start: float, end: float, frames: int = 8) -> list[float]:
    """Keep chronology and sample both ends without seeking beyond the source."""
    if not 1 <= frames <= 16 or start < 0 or end <= start:
        raise ValueError("Invalid frame request")
    return [round(start + (end - start) * (i + 0.5) / frames, 3) for i in range(frames)]


def segments(raw: list, start: float, end: float, offset: float = 0) -> list[dict]:
    """Normalize chunk offsets, filter to a window, and deduplicate overlapping speech."""
    result = []
    seen = set()
    for item in raw:
        try:
            left, right = float(item["start"]) + offset, float(item["end"]) + offset
            text = str(item["text"]).strip()
        except (KeyError, TypeError, ValueError):
            continue
        if (
            not text
            or not math.isfinite(left + right)
            or left < 0
            or right < left
            or right < start
            or left > end
        ):
            continue
        key = (round(left, 2), round(right, 2), text)
        if key not in seen:
            result.append({"start": left, "end": right, "text": text})
            seen.add(key)
    return sorted(result, key=lambda s: (s["start"], s["end"], s["text"]))


def audio_evidence(cached: dict | None, start: float, end: float) -> dict:
    """Missing, uncertain, and silent audio are explicit; frames remain usable."""
    if not cached:
        return {"state": "unavailable", "segments": []}
    state = cached.get("audio_state", "unavailable")
    raw = json.loads(cached.get("transcript") or "[]")
    return {
        "state": state,
        "segments": segments(raw, start, end),
        "source": "audio-story-cache",
    }


def fingerprint(asset: dict) -> str:
    """Key prepared frames by source bytes/version and extraction parameters."""
    return hashlib.sha256(
        json.dumps({"version": VERSION, "asset": asset}, sort_keys=True).encode()
    ).hexdigest()


def extract(packet: dict) -> dict:
    """Decode a verified source into bounded previews on the host holding originals."""
    root = Path(packet["library"]).resolve()
    source = (root / packet["locator"]).resolve()
    if not source.is_relative_to(root) or not source.is_file():
        raise ValueError("Source outside library or missing")
    stat = source.stat()
    if packet["fingerprint"] != f"stat:{stat.st_size}:{stat.st_mtime_ns}":
        raise ValueError("Source changed")
    photo = packet["kind"] == "photo"
    ranges = [(0, 0)] if photo else windows(packet["duration"])
    result = []
    for start, end in ranges:
        stamps = (
            [None]
            if photo
            else positions(start, end, min(8, max(1, int((end - start) * 2))))
        )
        frames = []
        for stamp in stamps:
            command = [
                "nice",
                "-n",
                "15",
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-threads",
                "1",
            ]
            if stamp is not None:
                command += ["-ss", str(stamp)]
            command += [
                "-i",
                str(source),
                "-map",
                "0:V:0",
                "-frames:v",
                "1",
                "-vf",
                "scale=768:768:force_original_aspect_ratio=decrease",
                "-threads",
                "1",
                "-f",
                "image2pipe",
                "-c:v",
                "mjpeg",
                "pipe:1",
            ]
            process = subprocess.run(
                command, capture_output=True, timeout=90, check=True
            )
            if not process.stdout or len(process.stdout) > 4 * 1024 * 1024:
                raise ValueError("Invalid frame size")
            frames.append(base64.b64encode(process.stdout).decode())
        result.append(
            {"start": start, "end": end, "positions": stamps, "frames": frames}
        )
    return {"version": VERSION, "windows": result}


def main() -> None:
    """Read a single private packet from stdin and emit its prepared evidence."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    sys.stdout.write(json.dumps(extract(json.load(sys.stdin))))


if __name__ == "__main__":
    main()
