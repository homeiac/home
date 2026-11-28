"""Prepare a private cricket release by merging only this feature into current review code."""

import argparse
import base64
import hashlib
import json
import logging
import shlex
import subprocess
import tempfile
from pathlib import Path

from .ledger import backup
from .prepare import save_private

BASE = "12750ed"


def merged_files(snapshot: dict, here: Path, resolved: Path | None = None) -> dict:
    """Three-way merge deployed fixes; refuse conflicts instead of overwriting newer UI work."""
    files = {}
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for name, live in snapshot["files"].items():
            base = subprocess.run(
                ["git", "show", BASE + ":scripts/knowledge-index/" + name],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            for filename, content in [
                ("live", live),
                ("base", base),
                ("ours", (here / name).read_text()),
            ]:
                (root / filename).write_text(content)
            result = subprocess.run(
                [
                    "git",
                    "merge-file",
                    "-p",
                    str(root / "live"),
                    str(root / "base"),
                    str(root / "ours"),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode:
                if resolved is None or not (resolved / name).is_file():
                    raise ValueError("Deployed UI merge needs review: " + name)
                content = (resolved / name).read_text()
                if any(
                    line.startswith(("<<<<<<<", "=======", ">>>>>>>"))
                    for line in content.splitlines()
                ):
                    raise ValueError("Unresolved deployment conflict: " + name)
                files[name] = content
            else:
                files[name] = result.stdout
    for path in sorted((here / "cricket").glob("*.py")):
        if not path.name.startswith(("test_", "demo")):
            files[str(path.relative_to(here))] = path.read_text()
    for path in sorted((here / "photo_enrichment/static").glob("cricket.*")):
        files[str(path.relative_to(here))] = path.read_text()
    return files


def main() -> None:
    """Build a reviewable payload first; apply only when --apply is explicitly selected."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--host")
    parser.add_argument(
        "--resolved",
        type=Path,
        help="Reviewed conflict resolutions against this exact snapshot",
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--ui-only",
        action="store_true",
        help="Update only cricket HTML/CSS/JS; leave analysis workers running",
    )
    args = parser.parse_args()
    here = Path(__file__).resolve().parent.parent
    snapshot = json.loads(args.snapshot.read_text())
    files = (
        {
            str(p.relative_to(here)): p.read_text()
            for p in sorted((here / "photo_enrichment/static").glob("cricket.*"))
        }
        if args.ui_only
        else merged_files(snapshot, here, args.resolved)
    )
    private = {}
    with tempfile.TemporaryDirectory() as directory:
        ledger = Path(directory) / "ledger.sqlite3"
        if not args.ui_only:
            backup(args.state / "ledger.sqlite3", ledger)
            private["ledger.sqlite3"] = base64.b64encode(ledger.read_bytes()).decode()
    for name in () if args.ui_only else ("people.json", "reference.jpg", "policy.json"):
        private[name] = base64.b64encode((args.state / name).read_bytes()).decode()
    for path in () if args.ui_only else (args.state / "evidence").iterdir():
        if path.suffix in {".json", ".jpg"}:
            private["evidence/" + path.name] = base64.b64encode(
                path.read_bytes()
            ).decode()
    release = (
        "cricket-"
        + hashlib.sha256(
            json.dumps(
                {"previous": snapshot["release"], "files": files}, sort_keys=True
            ).encode()
        ).hexdigest()[:16]
    )
    payload = {
        "previous": snapshot["release"],
        "hashes": snapshot["hashes"],
        "unit": snapshot["unit"],
        "release": release,
        "files": files,
        "private": private,
        "ui_only": args.ui_only,
    }
    save_private(args.output, payload)
    if args.apply:
        if not args.host:
            parser.error("--host required with --apply")
        remote = (here / "cricket/host_deploy.py").read_text()
        subprocess.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=10",
                args.host,
                "python3 -c " + shlex.quote(remote),
            ],
            input=json.dumps(payload),
            text=True,
            check=True,
        )
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger(__name__).info(
        "Prepared %s with %s files; apply=%s", release, len(files), args.apply
    )


if __name__ == "__main__":
    main()
