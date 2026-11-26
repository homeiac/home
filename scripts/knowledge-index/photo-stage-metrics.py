"""Export aggregate metrics from the private life-stage checkpoint."""

import argparse
from contextlib import closing
import math
from pathlib import Path
import sqlite3
import tempfile


STAGE = "life-stage"
STATES = ("pending", "running", "complete", "reused", "failed", "withheld")
HELP = {
    "knowledge_index_photo_stage_items": ("gauge", "Current photo count by processing stage and disposition."),
    "knowledge_index_photo_stage_completed_total": ("counter", "New successful results committed in the active stage run."),
    "knowledge_index_photo_stage_updated_timestamp_seconds": ("gauge", "Unix time of the most recent stage progress report."),
    "knowledge_index_photo_stage_phase_p95_seconds": ("gauge", "Observed p95 phase duration in seconds."),
}


def render(database: Path, progress_log: Path) -> str:
    """Read a consistent SQLite snapshot and emit no asset or identity labels."""
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True, timeout=10)) as conn:
        conn.execute("BEGIN")
        counts = dict(conn.execute("SELECT status, count(*) FROM jobs GROUP BY status"))
        if not counts or counts.keys() - set(STATES):
            raise ValueError("Unexpected life-stage checkpoint dispositions")
        durations = sorted(
            duration for (duration,) in conn.execute(
                "SELECT json_extract(outcome, '$.seconds') FROM jobs WHERE status = 'complete'"
            )
            if isinstance(duration, (float, int)) and math.isfinite(duration) and duration >= 0
        )
    lines = []

    def metric(name, samples):
        kind, help_text = HELP[name]
        lines.extend((f"# HELP {name} {help_text}", f"# TYPE {name} {kind}"))
        for labels, value in samples:
            lines.append(f'{name}{{stage="{STAGE}"{labels}}} {value}')

    metric("knowledge_index_photo_stage_items", [
        (f',state="{state}"', counts.get(state, 0)) for state in STATES
        if state != "running" or state in counts
    ])
    metric("knowledge_index_photo_stage_completed_total", [("", counts.get("complete", 0))])
    metric("knowledge_index_photo_stage_updated_timestamp_seconds", [("", progress_log.stat().st_mtime)])
    if durations:
        metric("knowledge_index_photo_stage_phase_p95_seconds", [
            (',phase="model_request"', durations[math.ceil(0.95 * len(durations)) - 1])
        ])
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--progress-log", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="Prometheus textfile path")
    args = parser.parse_args()
    metrics = render(args.database, args.progress_log)
    with tempfile.NamedTemporaryFile(mode="w", dir=args.out.parent, delete=False) as tmp:
        tmp.write(metrics)
    try:
        # The node exporter may run as a different user.
        Path(tmp.name).chmod(0o644)
        Path(tmp.name).replace(args.out)
    finally:
        Path(tmp.name).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
