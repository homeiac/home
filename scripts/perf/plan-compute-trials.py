#!/usr/bin/env python3
"""List the next sizing experiment for every stage and inventoried compute pool."""

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path


def host_cpus(inventory: Path) -> set[str]:
    """Read physical CPU pools once from the repository's Proxmox inventory."""
    section = ""
    hosts = set()
    for line in inventory.read_text().splitlines():
        line = line.strip()
        if line.startswith("["):
            section = line
        elif section == "[proxmox]" and line and not line.startswith("#"):
            address, separator, name = line.partition("#")
            if not (address.strip() and separator and len(name.split()) == 1):
                raise ValueError(f"Missing unique host name in {inventory}: {line}")
            hosts.add(name.strip() + "/cpu")
    if not hosts:
        raise ValueError(f"No Proxmox hosts found in {inventory}")
    return hosts


def plan(policy: dict, pools: set[str], today: date) -> list[tuple[str, str, str, str]]:
    """Produce a read-only trial queue. Missing evidence always gets an action."""
    rows = []
    for stage, spec in policy["stages"].items():
        records = spec["evidence"]
        unknown = records.keys() - pools
        if unknown:
            raise ValueError(
                f"{stage}: evidence refers to absent pools {sorted(unknown)}"
            )
        for pool in sorted(pools):
            record = records.get(pool)
            action, reason = "PREFLIGHT + CANARY", "No stage-specific evidence"
            if record:
                reason = record["reason"]
                state = record["state"]
                stale = record["profile"] != spec[
                    "profile"
                ] or today >= date.fromisoformat(record["review_on"])
                if stale:
                    action = "REASSESS"
                else:
                    action = {
                        "baseline": "TUNE BASELINE",
                        "candidate": "PREFLIGHT + CANARY",
                        "measured": "CHECK FLEET GAIN",
                        "deferred": "DEFER",
                        "excluded": "EXCLUDE",
                    }[state]
            rows.append((stage, pool, action, reason))
    return rows


def main() -> None:
    """Expand a versioned workload policy into a stage-by-pool action list."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("policy", type=Path)
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--inventory",
        action="store_true",
        help="Print stage coverage rather than a live decision",
    )
    group.add_argument(
        "--replay",
        type=Path,
        help="Replay observations or journal records with the common decision engine",
    )
    parser.add_argument(
        "--adapter-args",
        nargs=argparse.REMAINDER,
        default=[],
        help="Remaining arguments go to the workload snapshot adapter",
    )
    args = parser.parse_args()
    policy = json.loads(args.policy.read_text())
    if args.replay:
        from compute_feedback import replay

        for result in replay(args.replay, policy["feedback"]):
            print(json.dumps(result, sort_keys=True))
        return
    if not args.inventory and "feedback_adapter" in policy:
        from compute_feedback import choose

        adapter = args.policy.resolve().parent / policy["feedback_adapter"]
        raw = subprocess.check_output(
            [sys.executable, str(adapter), *args.adapter_args], text=True, timeout=45
        )
        sample = json.loads(raw)
        pool = choose(sample, policy["feedback"], set())
        print(
            json.dumps(
                {
                    "decision": "measure baseline" if pool else "hold",
                    "next_pool": pool,
                    "observation": sample,
                },
                sort_keys=True,
            )
        )
        return
    pools = set(policy["pools"])
    if inventory := policy.get("proxmox_inventory"):
        pools.update(host_cpus(args.policy.parent / inventory))
    if not pools or not policy["stages"]:
        parser.error("At least one compute pool and workload stage are required")
    for row in plan(policy, pools, args.as_of):
        print("\t".join(row))


if __name__ == "__main__":
    main()
