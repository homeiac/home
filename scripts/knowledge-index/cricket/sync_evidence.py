"""Copy only prepared evidence to the durable host; never synchronize review ledgers."""

import argparse
import shlex
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
            "--no-owner",
            "--no-group",
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
    # The review service drops CAP_DAC_OVERRIDE. Preserve private permissions but
    # make the remote service owner authoritative, not the laptop's numeric UID.
    normalize = """
import os
from pathlib import Path
root=Path('/local-3TB-backup/photo-enrichment/cricket/evidence')
os.chown(root,0,0);root.chmod(0o700)
for path in root.iterdir():
 if path.suffix in {'.json','.jpg'} and path.is_file() and not path.is_symlink():
  os.chown(path,0,0);path.chmod(0o600)
"""
    subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            args.host,
            "python3 -c " + shlex.quote(normalize),
        ],
        check=True,
        timeout=60,
    )


if __name__ == "__main__":
    main()
