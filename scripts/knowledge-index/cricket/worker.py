"""Hot-reload per-backend concurrency; drain extras without dropping in-flight results."""

import argparse
import base64
import fcntl
import hashlib
import json
import logging
import signal
import subprocess
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from .analyze import VERSION
from .jobs import claim, failed, heartbeat
from .ledger import Conflict, Ledger, encoded
from .prepare import save_private
from .reconcile import reconcile
from .trial import analyze_one


def policy(path: Path) -> dict:
    """Validate runtime bounds before accepting a desired worker count."""
    value = json.loads(path.read_text())
    if type(value.get("enabled")) is not bool or not isinstance(
        value.get("backends"), dict
    ):
        raise ValueError("Invalid runtime policy")
    for backend in value["backends"].values():
        maximum = backend["max_workers"]
        desired = backend["workers"]
        if (
            type(maximum) is not int
            or not 1 <= maximum <= 20
            or type(desired) is not int
            or not 0 <= desired <= maximum
        ):
            raise ValueError("Worker count exceeds configured resource bound")
    return value


def process(
    ledger: Ledger,
    album: dict,
    job: dict,
    backend: dict,
    evidence: Path,
    state: Path,
    portrait: str | None,
) -> dict:
    """Checkpoint each window, then reconcile proposals and complete the lease atomically."""
    prepared = json.loads((evidence / (job["asset"] + ".json")).read_text())
    items = []
    config_hash = hashlib.sha256(
        encoded(
            {
                "version": VERSION,
                "backend": {k: backend[k] for k in ("model", "api")},
                "evidence": prepared["cache_key"],
                "portrait": portrait,
            }
        ).encode()
    ).hexdigest()
    for index, window in enumerate(prepared["windows"]):
        target = state / "answers" / job["asset"] / config_hash / f"{index}.json"
        if target.exists():
            answer = json.loads(target.read_text())
        else:
            answer = analyze_one(
                {"asset": job, "window": window},
                backend,
                album["default_batter"],
                portrait,
            )
            save_private(target, answer)
        items.extend(answer["proposals"])
        heartbeat(ledger, job, index + 1)
    return reconcile(
        ledger,
        job["owner"],
        album["id"],
        job["asset"],
        job["fingerprint"],
        items,
        model=backend["model"],
        version=job["version"],
        run=config_hash,
        lease=job["lease"],
    )


def export(ledger: Ledger, folder: Path) -> None:
    """Publish effective rows, including immediate corrections, as an atomic private snapshot."""
    with ledger.connect() as db:
        albums = [dict(row) for row in db.execute("SELECT * FROM albums")]
    for album in albums:
        save_private(
            folder / (album["id"] + ".json"),
            {
                "owner": album["owner"],
                "album": album["id"],
                "events": ledger.list_events(album["owner"], album["id"]),
            },
        )


def main() -> None:
    """Run a single local dispatcher and save aggregate desired/active telemetry."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--portrait", type=Path)
    parser.add_argument("--version", default="cricket-v1")
    parser.add_argument("--until-idle", action="store_true")
    args = parser.parse_args()
    args.state.mkdir(parents=True, exist_ok=True, mode=0o700)
    fence = (args.state / "worker.lock").open("a")
    fcntl.flock(fence, fcntl.LOCK_EX | fcntl.LOCK_NB)
    ledger = Ledger(args.ledger)
    with ledger.connect() as db:
        albums = [dict(row) for row in db.execute("SELECT * FROM albums")]
    if len(albums) != 1:
        raise ValueError("Dispatcher requires one scoped album")
    album = albums[0]
    portrait = (
        base64.b64encode(args.portrait.read_bytes()).decode() if args.portrait else None
    )
    stopping = False

    def stop(*_: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    running: dict[Future, tuple[str, dict]] = {}
    started = time.monotonic()
    completed = 0
    errors = 0
    with ThreadPoolExecutor(max_workers=60) as pool:
        while True:
            for future, (name, job) in list(running.items()):
                if not future.done():
                    continue
                try:
                    future.result()
                    completed += 1
                except (
                    OSError,
                    ValueError,
                    KeyError,
                    TypeError,
                    subprocess.SubprocessError,
                    RuntimeError,
                ) as error:
                    try:
                        failed(ledger, job, type(error).__name__)
                    except Conflict:
                        # A reclaimed lease belongs to its new worker, including failure state.
                        pass
                    errors += 1
                    logging.getLogger(__name__).warning(
                        "Cricket job failed on %s: %s", name, type(error).__name__
                    )
                del running[future]
            try:
                config = policy(args.policy)
            except (OSError, ValueError, KeyError, TypeError):
                config = {"enabled": False, "backends": {}}
            active = {
                name: sum(n == name for n, _ in running.values())
                for name in set(config["backends"]) | {n for n, _ in running.values()}
            }
            desired = {
                name: config["backends"].get(name, {}).get("workers", 0)
                if config["enabled"] and not stopping
                else 0
                for name in active
            }
            for name, backend in config["backends"].items():
                for _ in range(max(0, desired[name] - active[name])):
                    job = claim(
                        ledger, album["owner"], album["id"], args.version, args.evidence
                    )
                    if job is None:
                        break
                    future = pool.submit(
                        process,
                        ledger,
                        album,
                        job,
                        backend,
                        args.evidence,
                        args.state,
                        portrait,
                    )
                    running[future] = (name, job)
                    active[name] += 1
            with ledger.connect() as db:
                states = dict(
                    db.execute(
                        "SELECT state,count(*) FROM jobs WHERE version=? GROUP BY state",
                        (args.version,),
                    )
                )
            save_private(
                args.state / "status.json",
                {
                    "time": time.time(),
                    "desired": desired,
                    "active": active,
                    "jobs": states,
                    "completed_this_run": completed,
                    "errors_this_run": errors,
                    "elapsed": time.monotonic() - started,
                },
            )
            export(ledger, args.state / "effective")
            if not running and (stopping or args.until_idle):
                break
            time.sleep(2)
    fence.close()


if __name__ == "__main__":
    main()
