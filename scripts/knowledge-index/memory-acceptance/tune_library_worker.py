"""Replay the production two-pass worker on the same private faces at each concurrency."""

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
import fcntl
import hashlib
import json
import os
import signal
import statistics
import subprocess
from pathlib import Path
import threading
import time
from unittest.mock import patch

import library_worker as worker
from library_backfill import connect
from review_openlabel import atomic_page


@contextmanager
def paused_worker(pause):
    """Restore only the previously loaded user agent, including when a trial fails."""
    label = "com.panderosystems.private-photo-library-worker"
    domain = f"gui/{os.getuid()}"
    service = f"{domain}/{label}"
    loaded = (
        pause
        and subprocess.run(
            ["launchctl", "print", service], capture_output=True
        ).returncode
        == 0
    )
    if loaded:
        subprocess.run(["launchctl", "bootout", service], check=True)
    try:
        yield
    finally:
        if loaded:
            plist = Path.home() / "Library/LaunchAgents" / (label + ".plist")
            subprocess.run(["launchctl", "bootstrap", domain, str(plist)], check=True)


def sample(root):
    """Include reviewed age groups, native actor-linked actions and two adult observations."""
    groups = defaultdict(list)
    with closing(connect(root)) as db:
        for raw, result, card_raw in db.execute(
            """
            SELECT j.input,j.outcome,r.card FROM jobs j JOIN reviewed r ON r.photo=j.photo
            WHERE j.status='reused' AND json_extract(j.outcome,'$.reviewed_action')=1 ORDER BY j.asset
        """
        ):
            row, result, card = map(json.loads, (raw, result, card_raw))
            if card["media_type"] != "Photo" or not result.get("stage"):
                continue
            uid = next(
                (
                    key
                    for key, f in card["faces"].items()
                    if row["id"] in (f.get("immich_face_id"), f.get("face_id"))
                ),
                None,
            )
            verbs = sorted(
                {
                    s["verb"]
                    for c in card["claims"] + card["individual"]
                    for s in c["spans"]
                    if "verb" in s and s.get("roles", {}).get("actor") == uid and uid
                }
            )
            if verbs:
                groups[result["stage"]].append((row, result["stage"], verbs))
        chosen = [entry for entries in groups.values() for entry in entries[:2]]
        adults = db.execute(
            """SELECT input FROM jobs WHERE status='complete' AND
                            json_extract(outcome,'$.stage')='adult' ORDER BY asset LIMIT 2"""
        )
        chosen.extend((json.loads(raw), None, []) for raw, in adults)
    if len(chosen) < 8:
        raise ValueError("Too few reviewed faces for a matched trial")
    return chosen


def summarize(runs, rows):
    """Pool wall time across passes and count exact stage matches on reviewed examples."""
    outcomes = [item for run in runs for item in run["results"]]
    successes = [item for item in outcomes if item["state"] == "complete"]
    reviewed = [item for item in outcomes if rows[item["index"]][1]]
    return {
        "lanes": runs[0]["slots"],
        "attempts": len(outcomes),
        "successful": len(successes),
        "per_min": round(60 * len(successes) / sum(run["seconds"] for run in runs), 2),
        "pass_rates": [round(run["rate"], 2) for run in runs],
        "reviewed_stage_exact": sum(
            item["state"] == "complete"
            and item["outcome"].get("stage") == rows[item["index"]][1]
            for item in reviewed
        ),
        "reviewed_attempts": len(reviewed),
        "median_seconds": {
            phase: round(
                statistics.median(item[phase] for item in outcomes if phase in item), 2
            )
            for phase in ("preview_seconds", "age_seconds", "action_seconds")
            if any(phase in item for item in outcomes)
        },
    }


def run(args):
    rows = json.loads(args.sample.read_text()) if args.sample else sample(args.root)
    args.out.mkdir(mode=0o700, parents=True, exist_ok=True)
    if (args.out / "sample.json").exists():
        raise ValueError("Choose a fresh output directory")
    atomic_page(args.out / "sample.json", json.dumps(rows))
    timings = threading.local()
    original_frames, original_observe = worker.frames, worker.observe

    def frames(row):
        started = time.monotonic()
        pics = original_frames(row)
        timings.item["preview_seconds"] = time.monotonic() - started
        timings.item["frame_hashes"] = [hashlib.sha256(pic).hexdigest() for pic in pics]
        return pics

    def observe(backend, endpoint, pics, prompt, schema):
        started = time.monotonic()
        try:
            answer = original_observe(
                backend,
                endpoint,
                pics,
                prompt,
                schema,
                images_first=timings.images_first,
            )
            timings.item["raw_age" if schema is worker.AGE_SCHEMA else "raw_action"] = (
                answer
            )
            return answer
        finally:
            timings.item[
                "age_seconds" if schema is worker.AGE_SCHEMA else "action_seconds"
            ] = (time.monotonic() - started)

    def trial(backend, endpoint, slots, sequence, name):
        def evaluate(index):
            timings.item = {}
            timings.images_first = args.images_first
            row = rows[index][0]
            try:
                state, outcome = worker.infer(
                    row, backend, endpoint, {}, lambda _: None
                )
            except (OSError, ValueError, KeyError, TypeError, IndexError) as err:
                state, outcome = "failed", {"error": type(err).__name__}
            return dict(index=index, state=state, outcome=outcome, **timings.item)

        start = time.monotonic()
        with ThreadPoolExecutor(slots) as lanes:
            results = list(lanes.map(evaluate, sequence))
        duration = time.monotonic() - start
        complete = sum(r["state"] == "complete" for r in results)
        report = dict(
            backend=backend,
            slots=slots,
            seconds=duration,
            complete=complete,
            rate=60 * complete / duration,
            results=results,
        )
        atomic_page(args.out / (backend + "-" + name + ".json"), json.dumps(report))
        print(
            backend,
            name,
            slots,
            complete,
            len(results),
            round(report["rate"], 2),
            flush=True,
        )

    def replay(backend, endpoint, baseline, candidate):
        forward = list(range(len(rows)))
        arms = (
            (("candidate-1", candidate), ("candidate-2", candidate))
            if args.images_first or args.candidate_only
            else (
                ("baseline-1", baseline),
                ("candidate-1", candidate),
                ("candidate-2", candidate),
                ("baseline-2", baseline),
            )
        )
        for label, slots in arms:
            sequence = forward if label.endswith("1") else forward[::-1]
            trial(backend, endpoint, slots, sequence, label)

    with patch.object(worker, "frames", frames), patch.object(
        worker, "observe", observe
    ), ThreadPoolExecutor(2) as backends:
        jobs = [
            backends.submit(
                replay,
                "mac-metal",
                "http://127.0.0.1:19476",
                args.baseline_mac,
                args.mac,
            ),
            backends.submit(
                replay, "rtx3070", args.rtx_endpoint, args.baseline_rtx, args.rtx
            ),
        ]
        for job in jobs:
            job.result()
    summary = {}
    for backend in ("mac-metal", "rtx3070"):
        for arm in ("baseline", "candidate"):
            paths = sorted(args.out.glob(f"{backend}-{arm}-*.json"))
            if paths:
                summary[f"{backend}/{arm}"] = summarize(
                    [json.loads(path.read_text()) for path in paths], rows
                )
    atomic_page(args.out / "aggregate.json", json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--baseline-mac", type=int, default=worker.DEFAULT_MAC_LANES)
    parser.add_argument("--baseline-rtx", type=int, default=worker.DEFAULT_RTX_LANES)
    parser.add_argument("--mac", type=int, default=6)
    parser.add_argument("--rtx", type=int, default=4)
    parser.add_argument("--rtx-endpoint", required=True)
    parser.add_argument(
        "--sample",
        type=Path,
        help="Repeat the exact private sample from a previous run",
    )
    parser.add_argument(
        "--candidate-only",
        action="store_true",
        help="Run two confirmation passes on the supplied fixed sample",
    )
    parser.add_argument(
        "--images-first",
        action="store_true",
        help="Measure the shared visual prefix twice against an existing baseline",
    )
    parser.add_argument(
        "--pause-worker",
        action="store_true",
        help="Pause the production LaunchAgent for this trial and restore it on exit",
    )
    os.umask(0o077)
    args = parser.parse_args()
    if args.pause_worker:

        def terminate(signum, _frame):
            raise SystemExit(128 + signum)

        signal.signal(signal.SIGTERM, terminate)
    if args.candidate_only or args.images_first:
        if not args.sample:
            parser.error("A confirmation run requires the baseline sample")
    if min(args.mac, args.rtx, args.baseline_mac, args.baseline_rtx) < 1:
        parser.error("Each backend needs at least one lane")
    with (args.root / "tuning.lock").open("a") as tuning_lock:
        fcntl.flock(tuning_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with paused_worker(args.pause_worker), (args.root / "worker.lock").open(
            "a"
        ) as worker_lock:
            fcntl.flock(worker_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            run(args)
