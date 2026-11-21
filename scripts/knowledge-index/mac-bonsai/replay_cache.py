"""Replay a contiguous pending queue sample against the frame-cache simulator on Piglet."""

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import sys
import time

ENRICHERS = Path(__file__).resolve().parents[1] / "enrichers"
sys.path.insert(0, str(ENRICHERS))
import media_summary
from pipeline_metrics import PipelineMetrics


def replay(index, library, limit, enricher, frames):
    metrics = PipelineMetrics(None, enricher)
    rows = media_summary.queue(index, enricher, limit)
    counts = Counter()
    payloads = {"photo": [], "video": []}
    started = time.monotonic()
    for row in rows:
        path = library / row["path"]
        kind = "video" if row["ext"] in media_summary.VIDEO_EXTS else "photo"
        try:
            if kind == "video":
                duration = media_summary.video_duration(path)
                n = max(1, min(frames, int(duration) or 1))
                images = [media_summary.jpeg_frame(path, duration * (i + 0.5) / n) for i in range(n)]
            else:
                images = [media_summary.jpeg_frame(path)]
        except (OSError, RuntimeError, ValueError, TimeoutError):
            counts["decode_errors"] += 1
            continue
        previous = metrics.mac_bytes
        keys = metrics.mac_request(images)
        # A serial replay assumes every successfully decoded transfer completed.
        metrics.mac_response(keys, kind, 0, {})
        payloads[kind].append(metrics.mac_bytes - previous)
        counts[kind] += 1
        counts["frames"] += len(images)

    def distribution(values):
        ordered = sorted(values)
        return (
            {
                label: ordered[math.ceil(q * len(ordered)) - 1]
                for label, q in (("p50", 0.5), ("p95", 0.95), ("max", 1))
            }
            if values
            else {}
        )

    print(
        json.dumps(
            dict(
                selected=len(rows),
                counts=dict(counts),
                seconds=time.monotonic() - started,
                base64_bytes=metrics.mac_bytes,
                reusable_bytes={mib: cache.reusable for mib, cache in metrics.mac_cache.items()},
                payload_bytes={kind: distribution(sizes) for kind, sizes in payloads.items()},
            )
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True)
    parser.add_argument("--library", required=True, type=Path)
    parser.add_argument("--enricher", required=True)
    parser.add_argument("--limit", type=int, default=512)
    parser.add_argument("--frames", type=int, default=8)
    args = parser.parse_args()
    replay(args.index, args.library, args.limit, args.enricher, args.frames)
