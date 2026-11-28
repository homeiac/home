#!/usr/bin/env python3
"""Score existing prediction receipts against pinned, held-out Waffles observations."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/perf"))
from otel_diagnosis import GPU, QUEUE, digest

DATA = ROOT / "docs/experiments/waffles"
FIFO = "d21253f8b0af575cc617d9726895de5aff5c1080"
ABA = "3a4c900272b8937304d16fdc67a9e936bf8f5307"


def queue_score(decision: dict, phases: list) -> dict:
    baseline, repaired = phases
    ratio = repaired["candidate_ms"] / baseline["candidate_ms"]
    rows = repaired["sort_rows"]
    gate = decision["gate"]
    supported = (baseline["returned_rows"] == repaired["returned_rows"] == 1
                 and ratio <= gate["max_after_before_claim_ratio"] and rows <= gate["max_after_sorted_rows"])
    rates = [round(p["completed_in_3m"] / 3, 1) for p in phases]
    return dict(supported=supported, lookup_ms=[baseline["candidate_ms"], repaired["candidate_ms"]],
                rows_sorted=[baseline["sort_rows"], rows], fleet_photos_per_min=rates,
                scope="Read-only candidate lookup; fleet rates are observational. Quality and lease parity unscored.")


def gpu_score(decision: dict, experiment: dict) -> dict:
    phases = [experiment["phases"][phase] for phase in ("before", "paused", "resumed")]
    metal, cpu = ([p["trials"][arm]["photos_per_minute"] for p in phases] for arm in ("mac-mps", "mac-cpu"))
    verify = experiment["verification"]
    restored = (verify["state"] == "complete" and verify["same_original_processes"]
                and verify["stopped"] == verify["resumed"] == 1 and experiment["resume_health_http"] == [200])
    agreement = experiment["binary_decisions_compared_per_trial"] == 52 and experiment["all_binary_decisions_identical"]
    gate = decision["gate"]
    supported = (experiment["state"] == "complete" and phases[1]["all_competitors_stopped"]
                 and metal[1] / metal[0] >= gate["min_isolated_over_before"]
                 and metal[1] / metal[2] >= gate["min_isolated_over_restored"]
                 and (not gate["require_smaller_cpu_gain"] or cpu[1] / cpu[0] < metal[1] / metal[0])
                 and (not gate["require_decision_agreement"] or agreement)
                 and (not gate["require_original_process_and_health_restored"] or restored))
    return dict(supported=supported, metal_photos_per_min=metal, cpu_photos_per_min=cpu,
                decisions_agree=agreement, original_process_restored=restored,
                scope="One matched A/B/A; pausing the competing process releases both CPU and GPU resources.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=["queue", "gpu"])
    parser.add_argument("receipt", type=Path)
    args = parser.parse_args()
    receipt = json.loads(args.receipt.read_text())
    checksum = receipt.pop("receipt_sha256")
    if digest(receipt) != checksum:
        parser.error("receipt checksum mismatch")
    frozen = json.loads((DATA / "otel-replay" / f"{args.case}.prediction.json").read_text())
    if checksum != frozen["receipt_sha256"]:
        parser.error("receipt differs from the registered historical prediction")
    decision = receipt["decision"]
    expected = {"queue": QUEUE, "gpu": GPU}[args.case]
    if decision["action"] != expected:
        result = dict(supported=False, scope="The proposed action differs from the tested intervention.")
    else:
        outcome = json.loads((DATA / "otel-replay" / f"{args.case}.outcome.json").read_text())
        if outcome["source_revision"] != (FIFO if args.case == "queue" else ABA):
            parser.error("unexpected held-out source revision")
        score = queue_score if args.case == "queue" else gpu_score
        result = score(decision, outcome["observations"])
    print(json.dumps(dict(receipt_sha256=checksum, outcome_revision=FIFO if args.case == "queue" else ABA,
                          result=result), indent=2, sort_keys=True))
    if not result["supported"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
