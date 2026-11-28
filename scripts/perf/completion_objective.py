"""Deterministic finish-time projection consumed by shared capacity qualification.

Adapters export counts from their existing stores. This module is offline: it
does not collect, publish, dispatch, or turn benchmark replays into production.
"""

import hashlib
import json
import math


def number(value: object) -> bool:
    """Accept finite nonnegative measurements, excluding JSON booleans."""
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def require(condition: bool, message: str) -> None:
    """Reject inconsistent accounting without echoing private evidence."""
    if not condition:
        raise ValueError(message)


def counts(value: object, total: object) -> bool:
    """Require a complete backend breakdown in the declared workload's one unit."""
    return (isinstance(value, dict) and bool(value)
            and all(isinstance(k, str) and k and number(v) for k, v in value.items())
            and number(total) and math.isclose(math.fsum(value.values()), total,
                                               rel_tol=1e-12, abs_tol=1e-12))


def project(objective: object, at_ns: int) -> dict:
    """Project the same remaining work at both combined production rates.

    Checkpoint-based ETA is diagnostic when native publication verification is
    absent. A complete structural receipt is still not qualification/admission;
    the caller must apply quality, peers, original controls, repeats and leases.
    """
    if objective is None:
        return {"decision": "hold", "reasons": ["completion objective missing"]}
    require(isinstance(objective, dict) and type(objective.get("version")) is int and objective["version"] == 1,
            "unsupported completion objective")
    require(type(at_ns) is int and at_ns > 0, "invalid projection cutoff")
    require(all(isinstance(objective.get(k), str) and objective[k].strip()
                for k in ("workload", "unit")), "completion workload/unit missing")
    remaining = objective.get("remaining", {})
    require(number(remaining.get("amount"))
            and type(remaining.get("observed_ns")) is int
            and 0 < remaining["observed_ns"] <= at_ns
            and isinstance(remaining.get("evidence_ref"), str) and remaining["evidence_ref"],
            "fixed remaining-work snapshot missing or after cutoff")
    increments = objective.get("increment_backends")
    require(isinstance(increments, list) and len(increments) == len(set(increments))
            and all(isinstance(k, str) and k for k in increments),
            "declare the added backends, including an empty list for in-place tuning")
    phases, reasons = {}, []
    for name in ("baseline", "trial"):
        phase = objective.get(name, {})
        start, end = phase.get("start_ns"), phase.get("end_ns")
        require(type(start) is int and type(end) is int and 0 < start < end <= at_ns,
                "invalid production measurement window")
        require(isinstance(phase.get("evidence_ref"), str) and phase["evidence_ref"],
                "production accounting evidence missing")
        total = phase.get("unique_production_completed")
        require(counts(phase.get("backend_unique_production_completed"), total),
                "backend production counts do not sum to unique workload output")
        verified = phase.get("verified_production_completed")
        breakdown = phase.get("backend_verified_production_completed")
        require(verified is None or number(verified) and verified <= total,
                "invalid verified production count")
        complete = counts(breakdown, verified)
        require(breakdown is None or complete, "verified backend accounting differs")
        require(not complete or all(value <= phase["backend_unique_production_completed"].get(k, -1)
                                    for k, value in breakdown.items()),
                "backend verification exceeds observed production")
        require(type(phase.get("evaluation_completed")) is int and phase["evaluation_completed"] >= 0,
                "record evaluation replays separately")
        complete = (complete and verified == total and isinstance(phase.get("readback_ref"), str)
                    and bool(phase["readback_ref"]))
        if not complete:
            reasons.append(name + ": independent production readback incomplete")
        duration = (end - start) / 1e9
        rate = total / duration
        require(math.isfinite(rate), "production rate overflow")
        eta = remaining["amount"] / rate if rate else None
        require(eta is None or math.isfinite(eta), "completion projection overflow")
        phases[name] = {"duration_s": duration, "unique_production_completed": total,
                        "verified_production_completed": verified,
                        "combined_production_per_s": rate,
                        "projected_remaining_s": eta,
                        "readback_complete": complete,
                        "evaluation_completed_excluded": phase["evaluation_completed"]}
    require(objective["baseline"]["end_ns"] <= objective["trial"]["start_ns"],
            "production windows overlap or are reversed")
    for backend in increments:
        values = objective["trial"].get("backend_verified_production_completed")
        if not isinstance(values, dict) or not number(values.get(backend)) or values[backend] <= 0:
            reasons.append(backend + ": no independently verified new production contribution")
    a, b = (phases[k]["projected_remaining_s"] for k in ("baseline", "trial"))
    delta = b - a if a is not None and b is not None else None
    if a is None or b is None:
        reasons.append("comparable positive production rates required")
    elif delta >= 0:
        reasons.append("no projected reduction in remaining completion time")
    if remaining["amount"] == 0:
        reasons.append("no remaining work to accelerate")
    fingerprint = hashlib.sha256(json.dumps(objective, sort_keys=True, separators=(",", ":"),
                                           allow_nan=False).encode()).hexdigest()
    return {"decision": "evidence_ready_not_admitted" if not reasons else "hold",
            "workload": objective["workload"], "unit": objective["unit"],
            "remaining_amount": remaining["amount"], "phases": phases,
            "projected_finish_delta_s": delta,
            "projected_finish_improvement_percent": -100 * delta / a if a and delta is not None else None,
            "evidence_sha256": fingerprint, "reasons": sorted(set(reasons)),
            "causal_bottleneck": "not established by throughput or utilization alone",
            "projection_scope": "same fixed remaining work; unique production only; evaluations excluded"}


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("objective", type=Path)
    parser.add_argument("--at-ns", required=True, type=int, help="fixed evidence cutoff; no live clock/query")
    args = parser.parse_args()
    try:
        result = project(json.loads(args.objective.read_text()), args.at_ns)
    except (OSError, KeyError, ValueError, TypeError) as error:
        parser.exit(2, "Completion projection failed (" + type(error).__name__ + ").\n")
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
