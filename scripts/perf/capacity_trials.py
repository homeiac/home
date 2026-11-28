"""Register bounded capacity experiments; registration never actuates or admits work."""

import hashlib
import json
import math
import os
import re
from pathlib import Path

from otel_diagnosis import digest

ACTION = "bounded-concurrency"
HASH = re.compile(r"[a-f0-9]{64}")
SECOND = 10**9


def require(condition: bool, message: str) -> None:
    """Reject incomplete contracts without including private evidence contents."""
    if not condition:
        raise ValueError(message)


def number(value: object) -> bool:
    """Accept finite nonnegative quantities, excluding booleans."""
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def text(value: object) -> bool:
    """Require an explicit nonempty identifier or private evidence pointer."""
    return isinstance(value, str) and bool(value.strip())


def integer(value: object, minimum: int = 0) -> bool:
    """Worker counts and timestamps cannot be fractions or JSON booleans."""
    return type(value) is int and value >= minimum


def closure(session: dict) -> tuple[set[str], set[str]]:
    """Resolve every dependency and declared peer from this immutable intake."""
    topology = session["topology"]
    require(len(session["requested"]) == 1, "register one serving pool per sweep")
    pending = list(session["requested"])
    resources, peers = set(), {session["workload"]}
    while pending:
        resource = pending.pop()
        require(resource in topology, "unknown resource in capacity closure")
        if resource in resources:
            continue
        resources.add(resource)
        peers.update(topology[resource]["workloads"])
        pending.extend(topology[resource]["uses"])
    require(resources == set(session["resources"]), "session resource closure changed")
    require(
        peers - {session["workload"]} == set(session["peers"]),
        "session peer set changed",
    )
    return resources, peers


def validate_spec(session: dict, spec: dict, at_ns: int) -> dict:
    """Derive a ceiling from fresh constraints after reserving the baseline footprint."""
    require(integer(at_ns, 1), "invalid registration time")
    resources, peers = closure(session)
    require(spec.get("action") == ACTION, "expected bounded concurrency action")
    require(
        spec.get("pool") == session["requested"][0],
        "capacity pool differs from session",
    )
    census = spec["callers"]
    require(
        isinstance(census, dict) and set(census) == resources,
        "incomplete physical caller census",
    )
    for resource, row in census.items():
        require(isinstance(row, dict), "invalid caller census")
        names = row.get("workloads")
        require(
            isinstance(names, list)
            and all(text(n) for n in names)
            and len(names) == len(set(names)),
            "invalid caller identities",
        )
        require(
            set(session["topology"][resource]["workloads"]) <= set(names),
            "caller census omits declared or scheduled workloads",
        )
        peers.update(names)
        fresh(row, at_ns)

    baseline = spec["baseline_allocation"]
    protected = spec["protected_allocation"]
    rollback = spec["rollback_allocation"]
    for vector in (baseline, protected, rollback):
        require(
            isinstance(vector, dict)
            and set(vector) == peers
            and all(integer(v) for v in vector.values()),
            "incomplete or invalid allocation vector",
        )
    require(rollback == baseline, "rollback must preserve the observed baseline")
    require(
        all(baseline[n] >= protected[n] for n in peers),
        "baseline reduces a protected reservation",
    )
    require(
        spec["baseline_mode"] in ("active", "observed_idle"),
        "unknown target baseline mode",
    )
    require(
        spec["baseline_mode"] != "observed_idle" or baseline[session["workload"]] == 0,
        "idle target must have zero observed workers",
    )
    fresh(spec["allocation_evidence"], at_ns)

    fixed = spec["fixed_inputs"]
    require(
        isinstance(fixed, dict)
        and set(fixed)
        == {
            "sources_sha256",
            "cohort_sha256",
            "model_sha256",
            "prompt_sha256",
            "extraction_sha256",
            "quality_sha256",
            "environment_sha256",
        }
        and all(isinstance(v, str) and HASH.fullmatch(v) for v in fixed.values()),
        "freeze source, cohort, model, prompt, extraction, quality and environment hashes",
    )

    limits = spec["limits"]
    require(
        integer(limits.get("window_s"), 300),
        "capacity windows require at least five minutes",
    )
    require(
        integer(limits.get("sample_gap_s"), 1) and limits["sample_gap_s"] <= 15,
        "capacity sampling must be at most fifteen seconds apart",
    )
    require(
        integer(limits.get("minimum_completed_items"), 10),
        "capacity requires ten durable completions",
    )
    for key in ("no_progress_s", "request_deadline_s", "drain_deadline_s"):
        require(
            integer(limits.get(key), 1),
            "missing bounded progress/request/drain deadline",
        )
    require(
        limits["drain_deadline_s"] >= limits["request_deadline_s"],
        "drain deadline precedes request deadline",
    )
    require(
        number(limits.get("max_peer_loss")) and limits["max_peer_loss"] <= 0.10,
        "peer throughput loss cannot exceed ten percent",
    )
    require(
        number(limits.get("max_peer_p95_growth"))
        and limits["max_peer_p95_growth"] <= 0.10,
        "peer latency growth cannot exceed ten percent",
    )
    require(
        limits.get("max_terminal_error_growth") == 0
        and type(limits["max_terminal_error_growth"]) in (int, float),
        "terminal error growth must be zero",
    )
    require(
        integer(spec["admission_deadline_ns"], at_ns + 1)
        and spec["admission_deadline_ns"] - at_ns <= 15 * SECOND,
        "initial admission needs a fresh registration within fifteen seconds",
    )
    require(
        integer(spec["completion_deadline_ns"], spec["admission_deadline_ns"] + 1),
        "missing experiment completion deadline",
    )

    constraints = spec["constraints"]
    require(
        isinstance(constraints, list) and bool(constraints),
        "missing measured resource constraints",
    )
    seen, ceilings = set(), []
    for constraint in constraints:
        resource, metric = constraint["resource"], constraint["metric"]
        require(
            resource in resources and text(metric) and (resource, metric) not in seen,
            "duplicate or out-of-scope constraint",
        )
        seen.add((resource, metric))
        fresh(constraint, at_ns)
        require(
            text(constraint.get("unit"))
            and number(constraint.get("capacity"))
            and number(constraint.get("per_extra_worker"))
            and constraint["per_extra_worker"] > 0,
            "constraint requires measured capacity, unit and positive incremental cost",
        )
        reservations = constraint["reserved"]
        require(
            isinstance(reservations, dict)
            and set(reservations) == peers
            and all(number(v) for v in reservations.values()),
            "constraint omits a baseline/scheduled reservation",
        )
        require(
            all(
                reservations[n] > 0
                for n in census[resource]["workloads"]
                if baseline[n] > 0
            ),
            "allocated or reserved workers require a measured resource footprint",
        )
        # Reserved is the measured full baseline footprint, including scheduled
        # floors and the target's incumbent workers. Costs remain in this row's unit.
        spare = constraint["capacity"] - math.fsum(reservations.values())
        require(spare >= 0, "baseline reservations exceed measured resource capacity")
        ceilings.append(math.floor(spare / constraint["per_extra_worker"]))
    require(
        {r for r, _ in seen} == resources, "missing physical dependency measurement"
    )
    target = session["workload"]
    ceiling = baseline[target] + min(ceilings)
    candidates = spec["candidates"]
    require(
        isinstance(candidates, list)
        and bool(candidates)
        and all(integer(n, baseline[target] + 1) for n in candidates),
        "invalid extra-worker candidates",
    )
    require(
        candidates == sorted(set(candidates), reverse=True)
        and candidates[0] == ceiling,
        "sweep must start at the derived ceiling and strictly descend",
    )
    minimum_duration = (
        2 * len(candidates) * limits["window_s"] + limits["drain_deadline_s"]
    )
    require(
        spec["completion_deadline_ns"] - spec["admission_deadline_ns"]
        >= minimum_duration * SECOND,
        "deadline cannot fit forward/reverse windows and drain",
    )
    require(
        spec.get("repeat_order") == "reverse-eligible"
        and spec.get("selection_tolerance") == 0.05,
        "repeat eligible candidates in reverse and select within five percent",
    )
    require(
        spec.get("output_accounting") == "fresh-evaluation-separate-from-production",
        "cached or duplicate production outputs cannot count as fresh evaluations",
    )

    lease = spec["lease"]
    require(
        isinstance(lease, dict)
        and lease.get("kind") == "KubernetesLease"
        and lease.get("state") == "planned"
        and text(lease.get("owner"))
        and text(lease.get("namespace")),
        "register planned ownership, not an acquired lease",
    )
    physical = {r for r in resources if not session["topology"][r]["uses"]}
    require(
        isinstance(lease.get("pools"), dict)
        and set(lease["pools"]) == physical
        and all(text(v) for v in lease["pools"].values())
        and len(set(lease["pools"].values())) == len(physical),
        "lease names must cover every physical pool uniquely",
    )
    require(
        integer(lease.get("duration_s"), 1)
        and integer(lease.get("renew_s"), 1)
        and lease["renew_s"] * 3 <= lease["duration_s"],
        "lease renewal needs bounded expiry margin",
    )
    return {
        "resources": sorted(resources),
        "affected": sorted(peers),
        "ceiling": ceiling,
        "candidate_allocations": [{**baseline, target: n} for n in candidates],
    }


def fresh(evidence: dict, at_ns: int) -> None:
    """Registration evidence must be current; admission must recheck it separately."""
    require(
        isinstance(evidence, dict)
        and integer(evidence.get("observed_ns"), 1)
        and 0 <= at_ns - evidence["observed_ns"] <= 15 * SECOND
        and text(evidence.get("evidence_ref"))
        and isinstance(evidence.get("evidence_sha256"), str)
        and HASH.fullmatch(evidence["evidence_sha256"]),
        "stale, future or missing capacity evidence",
    )


def validator_hash() -> str:
    """Fence receipts against changes to these validation rules."""
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def register(session: dict, spec: dict, at_ns: int, destination: Path) -> dict:
    """Seal a private immutable registration; never overwrite an earlier contract."""
    derived = validate_spec(session, spec, at_ns)
    body = {
        "schema": 1,
        "action": ACTION,
        "registered_ns": at_ns,
        "session_sha256": digest(session),
        "validator_sha256": validator_hash(),
        "spec": spec,
        "derived": derived,
        "decision": "registered_not_admitted",
    }
    receipt = {**body, "receipt_sha256": digest(body)}
    # Serialize first so invalid non-finite/unsupported extra values leave no file.
    encoded = json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False) + "\n"
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    return {
        "decision": receipt["decision"],
        "receipt_sha256": receipt["receipt_sha256"],
        "ceiling": derived["ceiling"],
        "candidates": spec["candidates"],
    }


def validate_receipt(session: dict, receipt: dict) -> dict:
    """Recompute a sealed contract; this is not live admission or quality approval."""
    body = {k: v for k, v in receipt.items() if k != "receipt_sha256"}
    require(
        receipt.get("receipt_sha256") == digest(body)
        and receipt.get("schema") == 1
        and receipt.get("action") == ACTION
        and receipt.get("decision") == "registered_not_admitted"
        and receipt.get("session_sha256") == digest(session)
        and receipt.get("validator_sha256") == validator_hash(),
        "capacity receipt scope or integrity changed",
    )
    derived = validate_spec(session, receipt["spec"], receipt["registered_ns"])
    require(
        derived == receipt.get("derived"),
        "derived capacity differs from measured constraints",
    )
    return derived
