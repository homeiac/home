"""Copy only prepared evidence to the durable host; never synchronize review ledgers."""

import argparse
import subprocess
from pathlib import Path


def main() -> None:
    """Use atomic rsync updates; the host ledger and runtime controls are out of scope."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--folder", type=Path, required=True)
    args = parser.parse_args()
    if not args.folder.is_dir():
        parser.error("Evidence folder missing")
    if args.host.startswith("-") or any(c.isspace() for c in args.host):
        parser.error("Invalid SSH target")
    subprocess.run(
        [
            "rsync",
            "-a",
            "--delay-updates",
            "--include=*.json",
            "--include=*.jpg",
            "--exclude=*",
            str(args.folder.resolve()) + "/",
            args.host + ":/local-3TB-backup/photo-enrichment/cricket/evidence/",
        ],
        check=True,
        timeout=900,
    )


if __name__ == "__main__":
    main()
