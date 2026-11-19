#!/usr/bin/env python3
"""Inspect or deploy the photo worker to an inventory-selected host (#217).

CB_HOST=root@<inventory-address> python3 scripts/knowledge-index/deploy-photo-worker.py --inspect
CB_HOST=root@<inventory-address> python3 scripts/knowledge-index/deploy-photo-worker.py --deploy
Uses existing SSH authentication. No camera configuration or caption-worker changes.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess


def main() -> None:
    """Send only reviewed application sources and the deployment helper over SSH."""
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--inspect", action="store_true")
    group.add_argument("--deploy", action="store_true")
    group.add_argument("--status", action="store_true")
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    files = {"photo-enrich.py": (here / "photo-enrich.py").read_text()}
    for path in sorted((here / "photo_enrichment").rglob("*")):
        if path.is_file() and path.suffix in (".py", ".js", ".css", ".html", ".txt", ".md"):
            files[str(path.relative_to(here))] = path.read_text()
    unit = (here / "host/photo-enrichment-worker.service").read_text()
    digest = hashlib.sha256(json.dumps([files, unit], sort_keys=True).encode()).hexdigest()[:16]
    payload = {"mode": "deploy" if args.deploy else "status" if args.status else "inspect",
               "files": files, "unit": unit, "release": digest}
    remote = (here / "host/rollout-photo-worker.py").read_text()
    subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", os.environ["CB_HOST"],
                    "python3 -c " + shlex.quote(remote)], input=json.dumps(payload), text=True, check=True)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode) from None
