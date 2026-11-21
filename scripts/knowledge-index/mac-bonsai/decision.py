"""Compare repeated factorial cells and select a throughput/latency operating point."""

import argparse
import json
import math
from pathlib import Path
import sqlite3


def decide(db):
    db.row_factory = sqlite3.Row
    cells = {}
    for slots, offered in db.execute(
        "SELECT DISTINCT slots,offered FROM mac_factorial_runs ORDER BY slots,offered"
    ):
        params = (slots, offered)
        runs = db.execute(
            "SELECT * FROM mac_factorial_runs WHERE slots=? AND offered=? ORDER BY block", params
        ).fetchall()
        if len(runs) != 2:
            raise ValueError(f"Waiting for both blocks for {params}")
        times = db.execute(
            "SELECT seconds FROM mac_factorial_items WHERE slots=? AND offered=? ORDER BY seconds", params
        ).fetchall()
        total_time = sum(r["seconds"] or 0 for r in runs)
        cells[params] = dict(
            slots=slots,
            offered=offered,
            valid=len(times),
            eligible=all(r["valid"] == 20 and r["error"] is None and r["peak_pressure"] == 1 for r in runs),
            captions_per_minute=60 * len(times) / total_time if total_time else None,
            p95_seconds=times[math.ceil(0.95 * len(times)) - 1][0] if times else None,
            peak_rss_mib=max(
                (r["peak_rss_mib"] for r in runs if r["peak_rss_mib"] is not None), default=None
            ),
            peak_pressure=max(
                (r["peak_pressure"] for r in runs if r["peak_pressure"] is not None), default=None
            ),
            errors=[r["error"] for r in runs],
            per_block=[r["per_minute"] for r in runs],
            mean_gpu_percent=sum((r["mean_gpu_percent"] or 0) * (r["seconds"] or 0) for r in runs)
            / total_time
            if total_time
            else None,
        )
    choices = [cell for cell in cells.values() if cell["eligible"]]
    if not choices:
        raise ValueError("No tested configuration qualified for production")
    fastest = max(c["captions_per_minute"] for c in choices)
    winner = min(
        (c for c in choices if c["captions_per_minute"] >= 0.95 * fastest),
        key=lambda c: (c["p95_seconds"], c["peak_rss_mib"]),
    )
    effects = {}
    for high in (20, 8, 4):
        corners = [(2, 2), (2, 20), (high, 2), (high, 20)]
        if not all(key in cells and cells[key]["eligible"] for key in corners):
            continue
        ll, lh, hl, hh = [cells[key]["captions_per_minute"] for key in corners]
        effects = dict(
            server_slots_high_level=high,
            server_slots=((hl - ll) + (hh - lh)) / 2,
            offered_requests=((lh - ll) + (hh - hl)) / 2,
            difference_in_differences=(hh - hl) - (lh - ll),
        )
        break
    return dict(
        selected=dict(slots=winner["slots"], offered=winner["offered"]),
        cells=list(cells.values()),
        effects_captions_per_minute=effects,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    args = parser.parse_args()
    with sqlite3.connect(args.database.resolve().as_uri() + "?mode=ro", uri=True) as con:
        print(json.dumps(decide(con), indent=2))
