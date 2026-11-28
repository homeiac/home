"""Manage the cricket queue and hot-reloaded worker policy without touching corrections."""

import argparse
import json
import logging
import re
import time
from pathlib import Path

from .ledger import Ledger, backup, restore
from .prepare import save_private
from .worker import policy


def status(ledger: Ledger) -> dict:
    """Return aggregate progress only, with no identities or transcript metric labels."""
    with ledger.connect() as db:
        jobs = [
            dict(r)
            for r in db.execute(
                "SELECT j.version,j.state,a.kind,count(*) AS assets,coalesce(sum(a.duration),0)/60 AS source_minutes "
                "FROM jobs j JOIN assets a ON a.owner=j.owner AND a.id=j.asset GROUP BY j.version,j.state,a.kind"
            )
        ]
        outcomes = dict(
            db.execute("SELECT review_state,count(*) FROM events GROUP BY review_state")
        )
        albums = [dict(r) for r in db.execute("SELECT owner,id FROM albums")]
    effective = {}
    for album in albums:
        for event in ledger.list_events(album["owner"], album["id"]):
            label = event["data"]["outcome"]
            effective[label] = effective.get(label, 0) + 1
    return {
        "captured_at": time.time(),
        "jobs": jobs,
        "review_states": outcomes,
        "effective_outcomes": effective,
    }


def retry(ledger: Ledger, version: str) -> int:
    """Reset only terminal errors; leave active leases, successful assets, and revisions alone."""
    with ledger.connect(True) as db:
        return db.execute(
            "UPDATE jobs SET state='queued',attempts=0,checkpoint='{}',error=NULL WHERE version=? AND state='error'",
            (version,),
        ).rowcount


def reanalyze(ledger: Ledger, policy_path: Path, version: str) -> int:
    """Add a fresh job generation and switch the dispatcher; preserve history and corrections."""
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", version) or version == "cricket-v1":
        raise ValueError("Choose a distinct analysis version")
    config = policy(policy_path)
    backup(
        ledger.path,
        ledger.path.parent
        / "backups"
        / ("before-" + version + "-" + str(time.time_ns()) + ".sqlite3"),
    )
    with ledger.connect(True) as db:
        count = db.execute(
            "INSERT OR IGNORE INTO jobs(owner,asset,version,stage) SELECT owner,id,?,'analyze' FROM assets",
            (version,),
        ).rowcount
    config["analysis_version"] = version
    save_private(policy_path, config)
    return count


def main() -> None:
    """Use explicit commands for status, pause/resume, live workers, retry and safe backups."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--policy", type=Path)
    parser.add_argument(
        "command",
        choices=[
            "status",
            "pause",
            "resume",
            "workers",
            "retry",
            "backup",
            "restore",
            "reanalyze",
        ],
    )
    parser.add_argument("--backend")
    parser.add_argument("--workers", type=int)
    parser.add_argument("--version", default="cricket-v1")
    parser.add_argument("--path", type=Path)
    args = parser.parse_args()
    if args.command == "restore":
        if args.path is None:
            parser.error("--path required")
        restore(args.path, args.ledger)
        return
    ledger = Ledger(args.ledger)
    result = {}
    if args.command in {"pause", "resume", "workers"}:
        if args.policy is None:
            parser.error("--policy required")
        config = policy(args.policy)
        if args.command == "workers":
            if args.backend not in config["backends"]:
                parser.error("Unknown backend")
            if (
                args.workers is None
                or not 0
                <= args.workers
                <= config["backends"][args.backend]["max_workers"]
            ):
                parser.error("Worker count exceeds measured bound")
            config["backends"][args.backend]["workers"] = args.workers
        else:
            config["enabled"] = args.command == "resume"
        save_private(args.policy, config)
        result = {
            "enabled": config["enabled"],
            "desired": {n: b["workers"] for n, b in config["backends"].items()},
        }
    elif args.command == "retry":
        result = {"retried": retry(ledger, args.version)}
    elif args.command == "reanalyze":
        if args.policy is None:
            parser.error("--policy required")
        result = {
            "queued": reanalyze(ledger, args.policy, args.version),
            "analysis_version": args.version,
        }
    elif args.command in {"backup", "restore"}:
        if args.path is None:
            parser.error("--path required")
        backup(args.ledger, args.path)
        result = {"completed": args.command}
    else:
        result = status(ledger)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger(__name__).info("%s", json.dumps(result))


if __name__ == "__main__":
    main()
