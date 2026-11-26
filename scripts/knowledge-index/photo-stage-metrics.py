"""Export aggregate metrics from the private life-stage checkpoint."""

import argparse
from contextlib import closing
import math
from pathlib import Path
import shlex
import sqlite3
import subprocess
import tempfile


STAGE = "life-stage"
TEXTFILE_DIRECTORY = "/var/lib/prometheus/node-exporter"
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


def write_textfile(metrics: str, out: Path) -> None:
    with tempfile.NamedTemporaryFile(mode="w", dir=out.parent, delete=False) as tmp:
        tmp.write(metrics)
    try:
        # The node exporter may run as a different user.
        Path(tmp.name).chmod(0o644)
        Path(tmp.name).replace(out)
    finally:
        Path(tmp.name).unlink(missing_ok=True)


def publish_textfile(metrics: str, host: str) -> None:
    """Send only aggregate metrics to an existing Prometheus textfile collector."""
    receiver = f"""
set -eu
umask 022
cd {shlex.quote(TEXTFILE_DIRECTORY)}
incoming=$(mktemp .photo-life-stage.XXXXXX)
trap 'rm -f "$incoming"' EXIT
cat > "$incoming"
test -s "$incoming"
chmod 0644 "$incoming"
mv -f "$incoming" knowledge_index_photo_stage_life_stage.prom
"""
    subprocess.run(
        ["/usr/bin/ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
         "--", host, "sh -c " + shlex.quote(receiver)],
        input=metrics, text=True, check=True, timeout=25,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--progress-log", type=Path, required=True)
    output = parser.add_mutually_exclusive_group(required=True)
    output.add_argument("--out", type=Path, help="Local Prometheus textfile path")
    output.add_argument("--ssh-host", help="Host with the existing Prometheus textfile collector")
    args = parser.parse_args()
    metrics = render(args.database, args.progress_log)
    if args.ssh_host:
        publish_textfile(metrics, args.ssh_host)
    else:
        write_textfile(metrics, args.out)


if __name__ == "__main__":
    main()
