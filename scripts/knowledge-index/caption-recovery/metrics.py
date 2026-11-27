"""Publish aggregate basic-caption recovery progress from the private SQLite ledger."""
import argparse
from contextlib import closing
import importlib
import os
from pathlib import Path
import plistlib
import sqlite3
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
publish = importlib.import_module("photo-stage-metrics").publish_textfile
STATES = ("verified", "already_described", "queued", "pending", "error", "generated", "excluded")
LABEL = "com.panderosystems.basic-caption-recovery-metrics"


def render(ledger: Path) -> str:
    """Report all cohort members in one read transaction, without file or person labels."""
    with closing(sqlite3.connect(ledger.resolve().as_uri() + "?mode=ro", uri=True, timeout=10)) as db:
        db.execute("BEGIN")
        counts = dict(db.execute("""SELECT coalesce(w.state,'pending'),count(*) FROM cohort c
            LEFT JOIN work w USING(id) WHERE c.cohort='caption' GROUP BY 1"""))
        rates = dict(db.execute("""SELECT json_extract(answer,'$.model'),count(*) / 15.0
            FROM work JOIN cohort USING(id) WHERE cohort='caption' AND answer IS NOT NULL
            AND unixepoch(json_extract(answer,'$.created')) BETWEEN unixepoch('now')-900 AND unixepoch('now')
            GROUP BY 1"""))
    if not counts or counts.keys() - set(STATES):
        raise ValueError("Empty recovery cohort or unknown disposition")
    name = "knowledge_index_caption_recovery_assets"
    lines = [f"# TYPE {name} gauge", *(f'{name}{{state="{s}"}} {counts.get(s,0)}' for s in STATES)]
    name = "knowledge_index_caption_recovery_saved_per_minute"
    lines.append(f"# TYPE {name} gauge")
    for model, backend in (("bonsai-27b-metal","Mac Metal"),("bonsai-27b","RTX 3070")):
        lines.append(f'{name}{{backend="{backend}"}} {rates.get(model,0)}')
    lines.extend(["# TYPE knowledge_index_caption_recovery_snapshot_seconds gauge",
                  f"knowledge_index_caption_recovery_snapshot_seconds {int(time.time())}"])
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", type=Path)
    parser.add_argument("--host", required=True)
    parser.add_argument("--install", action="store_true", help="Publish now and refresh every minute on this Mac")
    args = parser.parse_args()
    publish(render(args.ledger), args.host, filename="knowledge_index_caption_recovery.prom")
    if args.install:
        domain = f"gui/{os.getuid()}"
        path = Path.home()/"Library/LaunchAgents"/(LABEL + ".plist")
        config = dict(Label=LABEL, StartInterval=60, RunAtLoad=True,
                      ProgramArguments=[sys.executable, str(Path(__file__).resolve()), str(args.ledger.resolve()), "--host", args.host])
        wanted = plistlib.dumps(config)
        loaded = subprocess.run(["launchctl","print",domain+"/"+LABEL],capture_output=True).returncode == 0
        if path.exists() and path.read_bytes() == wanted and loaded:
            return
        if loaded:
            subprocess.run(["launchctl","bootout",domain+"/"+LABEL],check=True)
        path.write_bytes(wanted)
        subprocess.run(["launchctl","bootstrap",domain,str(path)],check=True)


if __name__ == "__main__":
    main()
