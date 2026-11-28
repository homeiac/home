"""Peer service budgets consume real service measurements, never synthetic completions."""

import math


def number(value: object) -> bool:
    """Accept finite nonnegative measurements, excluding JSON booleans."""
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def inactive(row: dict, phase: dict) -> bool:
    """An absent exporter is not an idle queue or an absent scheduled reservation."""
    proof = row.get("activity", {})
    if not isinstance(proof, dict):
        return False
    stamp = proof.get("observed_ns")
    return (
        all(type(phase.get(k)) is int for k in ("start_ns", "end_ns"))
        and proof.get("state") in {"idle", "finished"}
        and type(proof.get("runnable")) is int
        and proof["runnable"] == 0
        and number(proof.get("reservation_workers"))
        and isinstance(proof.get("evidence_ref"), str)
        and bool(proof["evidence_ref"].strip())
        and type(stamp) is int
        and phase["start_ns"] <= stamp <= phase["end_ns"]
        and phase["end_ns"] - stamp <= 15 * 10**9
    )


def assess_service(
    name: str, rows: list[dict], phases: list[dict], budgets: object
) -> tuple[list[str], list[str]]:
    """Evaluate declared absolute and relative service gates in their own units."""
    missing, regressions = [], []
    before, trial = rows
    if not isinstance(budgets, dict) or not budgets:
        return [f"{name}: service budgets missing"], []
    if any(
        type(p.get(k)) is not int for p in phases for k in ("start_ns", "end_ns")
    ) or any(p["end_ns"] <= p["start_ns"] for p in phases):
        return [f"{name}: invalid service sample window"], []
    if not before.get("cohort") or before.get("cohort") != trial.get("cohort"):
        missing.append(f"{name}: service input cohort changed or unknown")
    if any(row.get(k) is not True for row in rows for k in ("quality_ok", "slo_ok")):
        missing.append(f"{name}: missing or failed service baseline")
    if trial.get("quality_ok") is False or trial.get("slo_ok") is False:
        regressions.append(f"{name}: trial failed quality or service budget")
    measures = [row.get("service_metrics") for row in rows]
    if any(not isinstance(m, dict) or set(m) != set(budgets) for m in measures):
        return missing + [
            f"{name}: missing service measurements or changed metric set"
        ], regressions
    for metric, budget in budgets.items():
        label = f"{name}/{metric}"
        if (
            not isinstance(budget, dict)
            or not isinstance(budget.get("unit"), str)
            or not budget["unit"]
            or budget.get("direction") not in {"higher", "lower"}
            or not number(budget.get("max_regression"))
            or budget["max_regression"] > 0.10
            or not any(k in budget for k in ("min", "max"))
            or any(not number(budget[k]) for k in ("min", "max") if k in budget)
            or budget.get("min", 0) > budget.get("max", math.inf)
        ):
            missing.append(f"{label}: invalid or unbounded service budget")
            continue
        samples = [m[metric] for m in measures]
        valid = True
        for point, phase in zip(samples, phases, strict=True):
            minimum = (
                math.ceil((phase["end_ns"] - phase["start_ns"]) / (15 * 10**9)) + 1
            )
            if (
                not isinstance(point, dict)
                or point.get("unit") != budget["unit"]
                or not number(point.get("value"))
                or type(point.get("samples")) is not int
                or point["samples"] < minimum
                or not number(point.get("source_age_s"))
                or point["source_age_s"] > 15
                or not isinstance(point.get("evidence_ref"), str)
                or not point["evidence_ref"].strip()
            ):
                valid = False
        if not valid:
            missing.append(f"{label}: stale, absent or insufficient service samples")
            continue
        a, b = (p["value"] for p in samples)
        lower, upper = budget.get("min", 0), budget.get("max", math.inf)
        if not lower <= a <= upper:
            missing.append(f"{label}: baseline already exceeds service budget")
        if not lower <= b <= upper:
            regressions.append(f"{label}: absolute service budget exceeded")
        relative_failure = (
            b < a * (1 - budget["max_regression"])
            if budget["direction"] == "higher"
            else b > a * (1 + budget["max_regression"])
        )
        if relative_failure:
            regressions.append(f"{label}: relative service budget exceeded")
    return missing, regressions
