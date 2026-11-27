"""Local backup/restore commands; credentials and media never belong in arguments."""

import argparse
from pathlib import Path

from .ledger import Ledger, backup, restore


def main() -> None:
    """Initialize or copy a ledger without overwriting a running destination."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("init", "backup", "restore"))
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", nargs="?", type=Path)
    args = parser.parse_args()
    if args.action == "init":
        Ledger(args.source)
    elif args.destination is None:
        parser.error("backup and restore require a destination")
    else:
        {"backup": backup, "restore": restore}[args.action](
            args.source, args.destination
        )


if __name__ == "__main__":
    main()
