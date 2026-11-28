"""Protect every caller of the affected resources, including observed, unregistered callers."""
import json
import math
from pathlib import Path

from service_budgets import assess_service, inactive


def valid_number(value: object) -> bool:
    return type(value) in (float, int) and math.isfinite(value) and value >= 0


def assess(topology: dict, comparison: dict, watermark: int) -> dict:
    """Evaluate aligned before/trial windows from workload adapters in their own output units."""
    subject = comparison["subject"]
    resources = set()
    pending = list(comparison["resources"])
    while pending:
        resource = pending.pop()
        if resource not in resources:
            resources.add(resource)
            pending.extend(topology.get(resource, {}).get("uses", []))
    expected, discovered = set(), set()
    reasons, regressions = [], []
    phases = [comparison[k] for k in ("baseline", "trial")]
    if not resources or any(r not in topology for r in resources):
        reasons.append("unknown affected resource")
    for resource in resources:
        expected.update(topology.get(resource, {}).get("workloads", []))
        observed_sets = []
        # The serving-side inventory includes clients outside the static registry.
        for phase in phases:
            clients = phase["callers"].get(resource)
            if not isinstance(clients, list) or any(not isinstance(c, str) or not c for c in clients):
                reasons.append(f"incomplete caller census for {resource}")
            else:
                discovered.update(clients)
                observed_sets.append(set(clients))
        if len(observed_sets) == 2 and observed_sets[0] != observed_sets[1]:
            reasons.append(f"active caller mix changed on {resource}")
    affected = expected | discovered | {subject}
    if subject not in expected | discovered:
        reasons.append("subject has no observed or declared resource route")
    ends = [p["end_ns"] for p in phases]
    starts = [p["start_ns"] for p in phases]
    if (any(type(v) is not int for v in ends + starts)
            or not 0 < starts[0] < ends[0] <= starts[1] < ends[1] <= watermark
            or ends[0] - starts[0] != ends[1] - starts[1]
            or watermark - ends[1] > ends[1] - starts[1]):
        reasons.append("windows are stale, overlapping, unequal or outside the cutoff")
    if not phases[0].get("environment") or phases[0].get("environment") != phases[1].get("environment"):
        reasons.append("background configuration changed or unknown")
    cricket = subject == "cricket-indexer"
    if cricket:
        for phase in phases:
            gap = phase.get("max_sample_gap_s")
            if (not valid_number(gap) or gap > 15 or phase.get("warmed") is not True
                    or type(phase["start_ns"]) is not int or type(phase["end_ns"]) is not int
                    or phase["end_ns"] - phase["start_ns"] < 300 * 10**9):
                reasons.append("cricket requires five-minute warm windows and 15-second health sampling")
    changes = {}
    for name in sorted(affected):
        rows = [p["workloads"].get(name) for p in phases]
        if any(not isinstance(r, dict) or type(r.get("demand")) is not bool for r in rows):
            reasons.append(f"{name}: missing demand or workload telemetry")
            continue
        before, trial = rows
        if trial.get("baseline_preserved") is False:
            regressions.append(f"{name}: baseline allocation was reduced")
        elif trial.get("baseline_preserved") is not True:
            reasons.append(f"{name}: baseline allocation unverified")
        if before["demand"] != trial["demand"]:
            reasons.append(f"{name}: offered demand changed")
            continue
        if not before["demand"]:
            if name == subject or name in discovered:
                reasons.append(f"{name}: no comparable demand despite subject or caller activity")
            if cricket and any(not inactive(row, phase) for row, phase in zip(rows, phases)):
                reasons.append(f"{name}: idle state or scheduled reservation lacks fresh evidence")
            elif cricket and before["activity"]["reservation_workers"] != trial["activity"]["reservation_workers"]:
                reasons.append(f"{name}: scheduled reservation changed during comparison")
            continue
        kinds = {topology.get(resource, {}).get("measurement_kinds", {}).get(name, "indexer")
                 for resource in resources if name in topology.get(resource, {}).get("workloads", [])}
        if kinds - {"indexer", "service"} or len(kinds) > 1:
            reasons.append(f"{name}: conflicting or unknown measurement kind")
            continue
        if kinds == {"service"}:
            if name == subject:
                reasons.append(f"{name}: a service budget cannot replace target completion measurement")
                continue
            missing, losses = assess_service(name, rows, phases, comparison.get("service_budgets", {}).get(name))
            reasons.extend(missing)
            regressions.extend(losses)
            continue
        if cricket:
            if any(type(r.get("completed_items")) is not int or r["completed_items"] < 10 for r in rows):
                reasons.append(f"{name}: fewer than ten measured durable completions or count missing")
            if name != subject:
                if any(not valid_number(r.get(k)) for r in rows for k in ("p95_s", "terminal_error_rate")):
                    reasons.append(f"{name}: missing peer latency or terminal-error rate")
                elif (trial["p95_s"] > before["p95_s"] * 1.1
                      or trial["terminal_error_rate"] > before["terminal_error_rate"]):
                    regressions.append(f"{name}: peer latency or terminal-error budget exceeded")
        if any(not r.get("cohort") or not r.get("unit") for r in rows) or any(
                before[k] != trial[k] for k in ("cohort", "unit")):
            reasons.append(f"{name}: output unit or matched input cohort changed")
            continue
        if trial.get("quality_ok") is False or trial.get("slo_ok") is False:
            regressions.append(f"{name}: trial failed quality or service budget")
        if any(r.get(k) is not True for r in rows for k in ("quality_ok", "slo_ok")):
            reasons.append(f"{name}: missing or failed quality or service baseline")
            continue
        counts = [r.get("verified") for r in rows]
        if not all(valid_number(v) for v in counts) or counts[0] <= 0:
            reasons.append(f"{name}: insufficient verified output")
            continue
        change = counts[1] / counts[0] - 1
        changes[name] = round(100 * change, 4)
        floor = comparison["min_gain"] if name == subject else -comparison["max_peer_loss"]
        if cricket and name != subject:
            floor = max(floor, -0.10)
        if change + 1e-12 < floor:
            regressions.append(f"{name}: verified throughput missed declared threshold")
    # Incomparable evidence cannot establish a win. A demonstrated loss ends the canary.
    decision = "rollback" if regressions else "hold" if reasons else "eligible"
    return dict(decision=decision, resources=sorted(resources), affected=sorted(affected), verified_change_percent=changes,
                reasons=sorted(set(reasons + regressions)))


def shared_context(checkpoint: dict, watermark: int) -> dict:
    """Attach a separate fleet decision while keeping diagnostic receipts reproducible."""
    topology = checkpoint.get("topology") or json.loads(Path(__file__).with_name("shared-workloads.json").read_text())
    if "comparison" not in checkpoint:
        context = dict(decision="observe_only", registered_routes=topology,
                       next_trial="Vary one caller's extra in-flight requests or route a matched canary. Preserve all baseline allocations and the shared model service.",
                       reasons=["supply affected resources, caller census and per-workload windows"])
        if "activity_capture" in checkpoint:
            snapshot = json.loads(Path(checkpoint["activity_capture"]).read_text())
            age = watermark / 10**9 - snapshot["as_of_unix_s"]
            if 0 <= age <= 180:
                context["caller_observations"] = {
                    name: row["observations"] if (row["fresh"] and valid_number(row["source_age_s"])
                                                  and row["source_age_s"] + age <= 180) else None
                    for name, row in sorted(snapshot["workloads"].items())}
            else:
                context["reasons"].append("activity capture is stale or after the diagnosis cutoff")
        return context
    comparison = checkpoint["comparison"]
    for key in ("min_gain", "max_peer_loss"):
        if not valid_number(comparison[key]) or (key == "max_peer_loss" and comparison[key] > 1):
            raise ValueError(f"invalid {key}")
    return assess(topology, comparison, watermark)
