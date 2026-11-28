#!/usr/bin/env python3
"""Select a reversible diagnostic trial from an as-of OTLP JSONL capture."""
import argparse
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def digest(value: object) -> str:
    """Hash canonical JSON for portable evidence and decision receipts."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def attributes(items: list) -> dict:
    """Decode scalar OTLP attributes. Duplicate keys are ambiguous."""
    result = {}
    for item in items:
        key, box = item["key"], item["value"]
        if key in result:
            raise ValueError(f"duplicate attribute {key}")
        for kind in ("stringValue", "doubleValue", "intValue", "boolValue"):
            if kind in box:
                result[key] = int(box[kind]) if kind == "intValue" else box[kind]
                break
    return result


# Workload adapters supply measured aggregates as OTel log events. Stage fractions
# can also come directly from instrumented root and child spans (see below).
FIELDS = {
    "worker.cycle": ("samples", "cycle_s", "processing_s"),
    "db.claim.plan": ("latency_ms", "returned", "sort_input_rows", "order_keys"),
    "worker.profile": ("samples", "accelerator_stage_fraction"),
    "device.sample": ("utilization_pct", "worker_present"),
}


def number(value: object, upper: float = math.inf) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= upper


def validate(event: str, data: dict) -> None:
    for key in FIELDS[event]:
        value = data[key]
        if key == "order_keys":
            valid = isinstance(value, str)
        elif key == "worker_present":
            valid = isinstance(value, bool)
        elif key in ("samples", "returned", "sort_input_rows"):
            valid = type(value) is int and value >= 0
        else:
            valid = number(value, {"utilization_pct": 100, "accelerator_stage_fraction": 1}
                           .get(key, math.inf))
        if not valid:
            raise ValueError(f"invalid {event}.{key}")
    if event == "worker.cycle" and data["processing_s"] > data["cycle_s"]:
        raise ValueError("processing time exceeds the serial cycle")


def profile_spans(spans: dict) -> list:
    """Union direct accelerator child wall-times inside completed serial job roots."""
    children = defaultdict(list)
    for (scope, trace, _), span in spans.items():
        children[scope, trace, span[0]].append(span)
    profiled = []
    for (scope, trace, span_id), (_, begin, end, role) in spans.items():
        if role != "job":
            continue
        intervals = sorted((s, e) for _, s, e, r in children[scope, trace, span_id]
                           if r == "accelerator" and begin <= s < e <= end)
        if intervals:
            used, last = 0, begin
            for start, stop in intervals:
                used += max(0, stop - max(start, last))
                last = max(last, stop)
            profiled.append((scope, end, "worker.profile", {
                "samples": 1, "accelerator_stage_fraction": used / (end - begin)}))
    return profiled


def read_window(path: Path, cutoff: int, window_s: int) -> tuple:
    """Read Collector file-exporter records. Apply the event-time fence before decoding facts."""
    if cutoff <= 0 or window_s <= 0:
        raise ValueError("positive cutoff and window required")
    start = cutoff - window_s * 10**9
    facts, spans = [], {}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        packet = json.loads(line)
        if not ({"resourceLogs", "resourceSpans"} & packet.keys()):
            raise ValueError("expected an OTLP logs or traces request")
        for signal, groups, records in (("resourceLogs", "scopeLogs", "logRecords"),
                                        ("resourceSpans", "scopeSpans", "spans")):
            for resource in packet.get(signal, []):
                labels = attributes(resource["resource"].get("attributes", []))
                scope = tuple(labels.get(k) for k in ("service.name", "host.name", "workload.run.id"))
                for group in resource.get(groups, []):
                    for item in group.get(records, []):
                        t = int(item["endTimeUnixNano" if records == "spans" else "timeUnixNano"])
                        observed = int(item.get("observedTimeUnixNano", 0))
                        if not start < t <= cutoff or observed > cutoff or not all(scope):
                            continue
                        data = attributes(item.get("attributes", []))
                        if records == "spans":
                            begin = int(item["startTimeUnixNano"])
                            role = data.get("workload.stage")
                            if (role not in ("job", "accelerator") or not start < begin < t
                                    or item.get("status", {}).get("code") in (2, "STATUS_CODE_ERROR")):
                                continue
                            key = scope, item["traceId"].lower(), item["spanId"].lower()
                            value = item.get("parentSpanId", "").lower(), begin, t, role
                            if key in spans and spans[key] != value:
                                raise ValueError("conflicting spans with the same identity")
                            spans[key] = value
                        else:
                            event = item.get("eventName", data.get("event.name"))
                            if event in FIELDS:
                                fact = {key: data[key] for key in FIELDS[event]}
                                validate(event, fact)
                                facts.append((scope, t, event, fact))
    # Dedupe exact log re-exports. Independent job spans retain their own identities.
    unique = {digest(f): f for f in facts}
    facts = sorted([*unique.values(), *profile_spans(spans)], key=digest)
    scopes = {scope for scope, *_ in facts}
    if len(scopes) > 1:
        raise ValueError("select a single service, host and run per capture")
    return next(iter(scopes), ()), facts


QUEUE = "index_ready_fifo"
GPU = "isolate_accelerator_cotenant"


def decide(facts: list) -> dict:
    """Apply conservative rules; insufficient or conflicting signals select a probe."""
    groups = defaultdict(list)
    for _, timestamp, event, data in facts:
        groups[event].append((timestamp, data))
    cycles = [d for _, d in groups["worker.cycle"] if d["samples"] >= 10 and d["cycle_s"] > 0]
    plans = [d for _, d in groups["db.claim.plan"] if d["returned"] > 0]
    profiles = [d for _, d in groups["worker.profile"] if d["samples"] > 0]
    idle = [(t, d["utilization_pct"]) for t, d in groups["device.sample"] if not d["worker_present"]]
    gaps = [d["cycle_s"] - d["processing_s"] for d in cycles]
    waiting = bool(cycles) and all(g / c["cycle_s"] >= 0.5 for c, g in zip(cycles, gaps))
    sorted_claim = waiting and bool(plans) and all(
        p["order_keys"].strip() and p["sort_input_rows"] >= 100 * p["returned"]
        and p["latency_ms"] >= 500 * max(gaps) for p in plans)
    busy = len({t for t, _ in idle}) >= 2 and min(v for _, v in idle) >= 90
    model_bound = (sum(d["samples"] for d in profiles) >= 10
                   and all(d["accelerator_stage_fraction"] >= 0.5 for d in profiles))
    signals = {
        "cycle_gap_seconds": sorted(round(g, 4) for g in gaps),
        "successful_plan_ms": sorted(p["latency_ms"] for p in plans),
        "sorted_input_rows": sorted(p["sort_input_rows"] for p in plans),
        "order_keys": sorted({p["order_keys"] for p in plans}),
        "worker_absent_gpu_pct": [v for _, v in sorted(idle)],
        "accelerator_stage_fraction_range": ([round(fn(d["accelerator_stage_fraction"]
            for d in profiles), 4) for fn in (min, max)] if profiles else []),
    }
    candidates = []
    if sorted_claim:
        candidates.append(QUEUE)
    if busy and model_bound:
        candidates.append(GPU)
    if len(candidates) == 1:
        action = candidates[0]
        if action == QUEUE:
            trial = ("Canary an indexed, eligible-ready FIFO claim preserving the observed order "
                     "and a stable tie-breaker. Keep leases, retry eligibility and baseline workers.")
            gate = {"max_after_before_claim_ratio": 0.5, "max_after_sorted_rows": 0}
        else:
            trial = ("Inventory other device clients. Isolate one candidate briefly, replay matched "
                     "warmed inputs with a CPU control, then restore it and repeat.")
            gate = {"min_isolated_over_before": 1.1, "min_isolated_over_restored": 1.1,
                    "require_smaller_cpu_gain": True, "require_decision_agreement": True,
                    "require_original_process_and_health_restored": True}
        return dict(state="trial_proposed", action=action, trial=trial, gate=gate, evidence=signals)
    if len(candidates) > 1:
        probe = "Time both waits on the same jobs before selecting a single intervention."
    elif waiting:
        probe = "Capture a successful ready-claim query plan with timing, sort inputs and returned rows."
    elif groups["device.sample"] or profiles:
        probe = "Measure matched worker stages and sample device activity with the worker absent."
    else:
        probe = "Capture serial completion intervals and timed worker stages from the same pool."
    return dict(state="need_evidence", action=None, next_probe=probe, evidence=signals)


def predict(path: Path, cutoff: int, window_s: int) -> dict:
    scope, facts = read_window(path, cutoff, window_s)
    body = dict(schema=1, policy_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                as_of_unix_ns=str(cutoff), window_s=window_s, scope=scope,
                evidence_sha256=digest(facts), decision=decide(facts))
    return {**body, "receipt_sha256": digest(body)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--as-of", required=True, help="ISO 8601 timestamp with time zone")
    parser.add_argument("--window-seconds", default=600, type=int)
    parser.add_argument("--seal", type=Path, help="write new receipt; refuse to replace an existing one")
    args = parser.parse_args()
    timestamp = datetime.fromisoformat(args.as_of.replace("Z", "+00:00"))
    if timestamp.utcoffset() is None:
        parser.error("--as-of needs a timezone")
    cutoff = int(timestamp.timestamp()) * 10**9 + timestamp.microsecond * 1000
    receipt = json.dumps(predict(args.capture, cutoff, args.window_seconds), sort_keys=True, indent=2)
    if args.seal:
        with args.seal.open("x") as output:
            output.write(receipt + "\n")
    print(receipt)


if __name__ == "__main__":
    main()
