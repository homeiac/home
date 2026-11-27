"""Run matched private inference trials without publishing or changing reviewed highlights."""

import argparse
import base64
import hashlib
import json
import logging
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .analyze import VERSION, parse_reply, prompt, proposal
from .ledger import Ledger
from .models import infer
from .prepare import save_private
from .reactions import supplement


def sample(ledger: Ledger, evidence: Path, count: int) -> list[dict]:
    """Freeze a deterministic matched set of source windows and their content hashes."""
    with ledger.connect() as db:
        assets = {r["id"]: dict(r) for r in db.execute("SELECT * FROM assets")}
    rows = []
    for path in sorted(evidence.glob("*.json")):
        value = json.loads(path.read_text())
        asset = assets[value["asset"]]
        # First window per original avoids double-counting overlapping source minutes.
        window = value["windows"][0]
        rows.append(
            {
                "asset": asset,
                "window": window,
                "input_hash": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    if not rows:
        raise ValueError("No prepared evidence")
    return rows[: count or None]


def analyze_one(
    row: dict, backend: dict, default_batter: str, portrait: str | None
) -> dict:
    """Save raw observations and structured proposals, retaining individual validation failures."""
    start = time.monotonic()
    window = row["window"]
    photo = row["asset"]["kind"] == "photo"
    frames = ([portrait] if portrait else []) + window["frames"]
    raw = infer(backend, prompt(window, photo=photo, reference=bool(portrait)), frames)
    events = parse_reply(raw)
    proposals = []
    errors = []
    for event in events:
        try:
            proposals.append(
                proposal(
                    event,
                    row["asset"],
                    window,
                    default_batter,
                    reference=bool(portrait),
                )
            )
        except (TypeError, ValueError) as error:
            errors.append(type(error).__name__)
    if events and not proposals:
        raise ValueError("All model events failed validation")
    # Neutral descriptions of scenery are useful evidence, but are not cricket cards.
    useful = [
        p
        for p in proposals
        if p["data"]["role"] in {"batting", "bowling"}
        or p["data"]["outcome"] not in {"unknown", "other"}
    ]
    useful = supplement(useful, row["asset"], window, default_batter)
    return {
        "raw": raw,
        "proposals": useful,
        "invalid_events": errors,
        "seconds": time.monotonic() - start,
    }


def main() -> None:
    """Measure an explicit concurrency, preserving all answers privately for comparison."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--backend", required=True)
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--count", type=int, default=12)
    parser.add_argument(
        "--match",
        type=Path,
        help="Reuse exactly the input hashes from a previous trial manifest",
    )
    parser.add_argument("--portrait", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    backend = json.loads(args.policy.read_text())["backends"][args.backend]
    if not 1 <= args.workers <= backend["max_workers"]:
        parser.error("Workers exceed the measured backend bound")
    if args.output.exists():
        parser.error("Choose a fresh trial output directory")
    ledger = Ledger(args.ledger)
    with ledger.connect() as db:
        albums = list(db.execute("SELECT * FROM albums"))
    if len(albums) != 1:
        raise ValueError("Trial requires one explicit album")
    actor = albums[0]["default_batter"]
    portrait = (
        base64.b64encode(args.portrait.read_bytes()).decode() if args.portrait else None
    )
    rows = sample(ledger, args.evidence, 0 if args.match else args.count)
    if args.match:
        frozen = json.loads(args.match.read_text())["hashes"]
        by_hash = {r["input_hash"]: r for r in rows}
        if any(h not in by_hash for h in frozen):
            raise ValueError("Frozen trial inputs changed or disappeared")
        rows = [by_hash[h] for h in frozen]
    args.output.mkdir(parents=True, mode=0o700)
    manifest = {
        "version": VERSION,
        "backend": args.backend,
        "workers": args.workers,
        "hashes": [r["input_hash"] for r in rows],
        "portrait_hash": hashlib.sha256(args.portrait.read_bytes()).hexdigest()
        if args.portrait
        else None,
    }
    save_private(args.output / "inputs.json", manifest)

    def run(pair: tuple[int, dict]) -> dict:
        i, row = pair
        try:
            result = analyze_one(row, backend, actor, portrait)
            result["ok"] = True
        except (
            OSError,
            ValueError,
            KeyError,
            TypeError,
            subprocess.SubprocessError,
            RuntimeError,
        ) as error:
            result = {"ok": False, "error": type(error).__name__}
        save_private(args.output / f"{i:03}.json", result)
        return result

    start = time.monotonic()
    with ThreadPoolExecutor(args.workers) as pool:
        results = list(pool.map(run, enumerate(rows)))
    elapsed = time.monotonic() - start
    success = sum(r["ok"] for r in results)
    covered = sum(
        r["window"]["end"] - r["window"]["start"]
        for r, v in zip(rows, results)
        if v["ok"]
    )
    summary = {
        **{k: v for k, v in manifest.items() if k not in {"hashes", "portrait_hash"}},
        "attempted": len(rows),
        "completed": success,
        "seconds": round(elapsed, 2),
        "completed_per_minute": round(60 * success / elapsed, 2),
        "source_minutes_per_minute": round(covered / elapsed, 3),
        "errors": len(rows) - success,
    }
    save_private(args.output / "summary.json", summary)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger(__name__).info("%s", json.dumps(summary))
    if success < len(rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
