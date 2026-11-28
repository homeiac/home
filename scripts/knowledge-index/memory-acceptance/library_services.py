"""Install the private Mac reader, resumable worker, and shared stage telemetry."""

import argparse
from contextlib import closing
import importlib
import os
from pathlib import Path
import plistlib
import subprocess
import sys

from library_backfill import HERE, connect
from review_openlabel import atomic_page

metrics = importlib.import_module("photo-stage-metrics")


def report(root, host):
    progress = root / "progress"
    if progress.exists():
        text = metrics.render(
            root / "library.sqlite3", progress, "library-face-observations"
        )
        metrics.publish_textfile(text, host, "library-face-observations")
    with closing(connect(root)) as db:
        count, pending = db.execute(
            "SELECT count(*),sum(NOT ocr_done) FROM photos"
        ).fetchone()
    stage = "library-ocr-tags"
    samples = {
        "knowledge_index_photo_stage_items": [
            (
                f',state="{state}"',
                (
                    pending
                    if state == "pending"
                    else count - pending if state == "reused" else 0
                ),
            )
            for state in metrics.STATES
        ],
        "knowledge_index_photo_stage_updated_timestamp_seconds": [
            ("", (root / "inventory-updated").stat().st_mtime)
        ],
    }
    lines = []
    for name, values in samples.items():
        kind, help_text = metrics.HELP[name]
        lines.extend([f"# HELP {name} {help_text}", f"# TYPE {name} {kind}"])
        lines.extend(
            f'{name}{{stage="{stage}"{label}}} {value}' for label, value in values
        )
    metrics.publish_textfile("\n".join(lines) + "\n", host, stage)


def install(root, rtx, host):
    user = f"gui/{os.getuid()}"
    programs = [
        ("worker", "library_worker.py", ["--rtx", rtx], 60),
        ("review", "library_review.py", [], 30),
        ("metrics", "library_services.py", ["--metrics-host", host, "--report"], 60),
    ]
    for short, script, params, interval in programs:
        label = "com.panderosystems.private-photo-library-" + short
        plist = Path.home() / "Library/LaunchAgents" / (label + ".plist")
        config = dict(
            Label=label,
            ProgramArguments=[sys.executable, str(HERE / script), str(root), *params],
            RunAtLoad=True,
            StartInterval=interval,
            WorkingDirectory=str(root),
            StandardOutPath=str(root / (short + ".log")),
            StandardErrorPath=str(root / (short + ".log")),
            EnvironmentVariables={
                "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
            },
        )
        payload = plistlib.dumps(config).decode()
        loaded = (
            subprocess.run(
                ["launchctl", "print", user + "/" + label], capture_output=True
            ).returncode
            == 0
        )
        if loaded and plist.exists() and plist.read_text() == payload:
            continue
        if loaded:
            subprocess.run(["launchctl", "bootout", user + "/" + label], check=True)
        atomic_page(plist, payload)
        subprocess.run(["launchctl", "bootstrap", user, str(plist)], check=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("root", type=Path)
    ap.add_argument("--metrics-host", required=True)
    ap.add_argument("--rtx")
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()
    os.umask(0o077)
    if args.report:
        report(args.root, args.metrics_host)
    elif args.rtx:
        install(args.root.resolve(), args.rtx, args.metrics_host)
    else:
        ap.error("installation requires an RTX endpoint")
