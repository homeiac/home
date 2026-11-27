"""Stop only a named private cricket trial and its request subprocesses, retaining trial evidence."""

import argparse
import json
import os
import signal
import subprocess
import time
from pathlib import Path

from .prepare import save_private


def main() -> None:
    """Cancel an unproductive trial without touching model servers or existing backfills."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()
    manifest = json.loads((args.output / "inputs.json").read_text())
    process = subprocess.run(
        ["ps", "-axo", "pid=,ppid=,args="], capture_output=True, text=True, check=True
    )
    rows = [
        line.strip().split(None, 2)
        for line in process.stdout.splitlines()
        if line.strip()
    ]
    targets = {
        int(pid)
        for pid, parent, command in rows
        if " -m cricket.trial " in command
        and str(args.output) in command
        and " -c " not in command
    }
    if len(targets) != 1:
        raise ValueError("Expected exactly one matching cricket trial")
    root = set(targets)
    while True:
        descendants = {
            int(pid) for pid, parent, command in rows if int(parent) in targets
        }
        if descendants <= targets:
            break
        targets.update(descendants)
    for pid in sorted(targets - root):
        os.kill(pid, signal.SIGTERM)
    for pid in root:
        os.kill(pid, signal.SIGTERM)
    results = [json.loads(p.read_text()) for p in args.output.glob("[0-9]*.json")]
    save_private(
        args.output / "aborted.json",
        {
            "version": manifest["version"],
            "workers": manifest["workers"],
            "reason": args.reason,
            "returned": len(results),
            "completed": sum(r.get("ok", False) for r in results),
            "seconds": round(
                time.time() - (args.output / "inputs.json").stat().st_mtime, 2
            ),
        },
    )


if __name__ == "__main__":
    main()
