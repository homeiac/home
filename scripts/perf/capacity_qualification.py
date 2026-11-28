"""Offline capacity qualification and ranking; these helpers never admit a trial."""

from dataclasses import dataclass, replace

from capacity_trials import ACTION, integer, number, require, validate_receipt
from otel_diagnosis import digest
from service_budgets import inactive


@dataclass(frozen=True)
class CandidateContext:
    """Validated per-comparison policy, passed internally rather than read from JSON."""

    comparison_sha256: str
    topology_sha256: str
    idle_target: bool
    reservation: int
    minimum_items: int
    sample_gap_s: int
    window_s: int
    max_peer_p95_growth: float

    def matches(self, comparison: dict, topology: dict) -> None:
        """Prevent reuse after mutation or for a different resource graph."""
        require(
            self.comparison_sha256 == digest(comparison)
            and self.topology_sha256 == digest(topology),
            "capacity comparison changed after validation",
        )

    def target(
        self, rows: list[dict], phases: list[dict]
    ) -> tuple[list[str], list[str], float | None]:
        """Require useful fresh output without demanding growth over a faster candidate."""
        before, trial = rows
        missing, losses = [], []
        if self.idle_target:
            if (
                before["demand"] is not False
                or trial["demand"] is not True
                or not inactive(before, phases[0])
                or before.get("verified") != 0
                or type(before.get("verified")) not in (int, float)
                or before.get("completed_items") != 0
                or type(before.get("completed_items")) is not int
                or before.get("activity", {}).get("reservation_workers")
                != self.reservation
            ):
                missing.append(
                    "target lacks fresh observed-idle evidence and its protected reservation"
                )
        elif not all(row["demand"] for row in rows):
            missing.append("active target has missing or changed demand")
        measured = [trial] if self.idle_target else rows
        if any(
            not integer(r.get("completed_items"), self.minimum_items)
            or not integer(r.get("fresh_inference_items"), self.minimum_items)
            or r["completed_items"] != r["fresh_inference_items"]
            for r in measured
        ):
            missing.append(
                "target needs matching durable fresh-inference completions; cached outputs cannot count"
            )
        if any(not number(r.get("verified")) or r["verified"] <= 0 for r in measured):
            missing.append("target has insufficient verified useful output")
        if (
            not before.get("unit")
            or before.get("unit") != trial.get("unit")
            or not before.get("cohort")
            or before.get("cohort") != trial.get("cohort")
        ):
            missing.append("target input cohort or output unit differs")
        if any(trial.get(k) is False for k in ("quality_ok", "slo_ok")):
            losses.append("target failed quality or service budget")
        if any(r.get(k) is not True for r in rows for k in ("quality_ok", "slo_ok")):
            missing.append("target quality rubric or service qualification is missing")
        if any(not number(r.get("terminal_error_rate")) for r in measured):
            missing.append("target terminal-error rate is missing")
        elif trial["terminal_error_rate"] > (
            0 if self.idle_target else before["terminal_error_rate"]
        ):
            losses.append("target terminal-error rate increased")
        change = None
        if (
            not self.idle_target
            and all(number(r.get("verified")) for r in rows)
            and before["verified"] > 0
        ):
            change = 100 * (trial["verified"] / before["verified"] - 1)
        return missing, losses, change


def context(session: dict, receipt: dict, comparison: dict) -> CandidateContext:
    """Bind an immutable registration to allocations and fixed inputs for one candidate."""
    derived = validate_receipt(session, receipt)
    spec = receipt["spec"]
    target = session["workload"]
    reference = comparison.get("peer_baseline")
    require(
        isinstance(reference, dict)
        and digest(reference) == spec["peer_baseline_sha256"],
        "missing or changed original protected baseline",
    )
    require(
        integer(reference.get("end_ns"), 1)
        and 0 <= receipt["registered_ns"] - reference["end_ns"] <= 15 * 10**9
        and reference.get("allocation") == spec["baseline_allocation"]
        and reference.get("environment") == spec["fixed_inputs"]["environment_sha256"]
        and reference["workloads"][target].get("cohort")
        == spec["fixed_inputs"]["cohort_sha256"],
        "protected baseline is stale or differs from registered inputs/allocations",
    )
    require(
        comparison.get("action") == ACTION
        and comparison.get("subject") == target
        and comparison.get("resources") == session["requested"]
        and comparison.get("capacity_registration_sha256") == receipt["receipt_sha256"],
        "capacity comparison does not match the registration",
    )
    require(
        comparison.get("fixed_inputs") == spec["fixed_inputs"]
        and comparison.get("output_accounting") == spec["output_accounting"],
        "capacity inputs or output accounting changed",
    )
    require(
        number(comparison.get("max_peer_loss"))
        and comparison["max_peer_loss"] <= spec["limits"]["max_peer_loss"],
        "comparison weakens the registered peer throughput budget",
    )
    require(
        number(comparison.get("min_gain")) and comparison["min_gain"] == 0,
        "capacity qualification uses separate ranking, not a target growth threshold",
    )
    require(
        comparison.get("service_budgets", {}) == spec.get("service_budgets", {}),
        "service budgets differ from the registered contract",
    )
    allocations = []
    for phase_name in ("baseline", "trial"):
        phase = comparison[phase_name]
        allocation = phase.get("allocation")
        require(
            isinstance(allocation, dict)
            and set(allocation) == set(derived["affected"])
            and all(integer(v) for v in allocation.values()),
            "missing observed allocation vector",
        )
        require(
            all(
                allocation[n] == spec["baseline_allocation"][n]
                for n in allocation
                if n != target
            )
            and allocation[target] >= spec["protected_allocation"][target],
            "candidate changed a protected or peer allocation",
        )
        require(
            phase.get("environment") == spec["fixed_inputs"]["environment_sha256"]
            and phase["workloads"][target].get("cohort")
            == spec["fixed_inputs"]["cohort_sha256"],
            "candidate environment or frozen target cohort changed",
        )
        require(
            all(
                set(names) <= set(derived["affected"])
                for names in phase["callers"].values()
            ),
            "new caller requires a new registration",
        )
        allocations.append(allocation)
    require(
        allocations[1] in derived["candidate_allocations"],
        "trial allocation was not registered",
    )
    require(
        allocations[0] == spec["baseline_allocation"]
        or allocations[0] in derived["candidate_allocations"],
        "comparison baseline allocation was not registered",
    )
    initial = allocations[0] == spec["baseline_allocation"]
    before, trial = comparison["baseline"], comparison["trial"]
    require(
        all(
            integer(trial.get(k), 1)
            for k in ("admitted_ns", "warmup_start_ns", "warmup_end_ns")
        )
        and receipt["registered_ns"] <= trial["admitted_ns"]
        and before["end_ns"]
        <= trial["admitted_ns"]
        <= trial["warmup_start_ns"]
        <= trial["warmup_end_ns"]
        <= trial["start_ns"]
        and trial["start_ns"] - trial["admitted_ns"]
        <= spec["limits"]["warmup_deadline_s"] * 10**9,
        "missing or unbounded admission/warmup timing",
    )
    require(
        all(
            integer(p.get(k), 1)
            for p in (before, trial)
            for k in ("start_ns", "end_ns")
        )
        and receipt["registered_ns"]
        <= trial["start_ns"]
        < trial["end_ns"]
        <= spec["completion_deadline_ns"],
        "candidate falls outside the registered experiment deadline",
    )
    if initial:
        require(
            digest(before) == spec["peer_baseline_sha256"],
            "initial comparison changed the protected baseline",
        )
        require(
            0 <= receipt["registered_ns"] - before["end_ns"] <= 15 * 10**9
            and trial["admitted_ns"] <= spec["admission_deadline_ns"]
            and allocations[1][target] == derived["ceiling"],
            "first candidate must start at the measured maximum after a fresh baseline",
        )
    else:
        require(
            before["start_ns"] >= receipt["registered_ns"],
            "candidate baseline predates registration",
        )
    idle = (
        spec["baseline_mode"] == "observed_idle"
        and allocations[0] == spec["baseline_allocation"]
    )
    return CandidateContext(
        digest(comparison),
        digest(session["topology"]),
        idle,
        spec["protected_allocation"][target],
        spec["limits"]["minimum_completed_items"],
        spec["limits"]["sample_gap_s"],
        spec["limits"]["window_s"],
        spec["limits"]["max_peer_p95_growth"],
    )


def qualify(session: dict, receipt: dict, comparison: dict, watermark: int) -> dict:
    """Run peer-preserving candidate checks without authorizing execution or selection."""
    from shared_workloads import shared_context

    validated = context(session, receipt, comparison)
    result = shared_context(
        {"topology": session["topology"], "comparison": comparison},
        watermark,
        capacity=validated,
    )
    # Pairwise checks alone allow 100 -> 90 -> 81 throughput or repeated p95
    # growth. Compare every candidate with the same real protected baseline too.
    anchored = {**comparison, "baseline": comparison["peer_baseline"]}
    original = replace(
        validated,
        comparison_sha256=digest(anchored),
        idle_target=receipt["spec"]["baseline_mode"] == "observed_idle",
    )
    protected = shared_context(
        {"topology": session["topology"], "comparison": anchored},
        watermark,
        capacity=original,
    )
    priority = {"eligible": 0, "hold": 1, "rollback": 2}
    if priority[protected["decision"]] > priority[result["decision"]]:
        result["decision"] = protected["decision"]
    result["reasons"] += [
        "protected baseline: " + reason for reason in protected["reasons"]
    ]
    return {
        "decision": "not_admitted",
        "candidate_review": result,
        "protected_baseline_review": protected,
        "pending": [
            "phase_order_and_repetition",
            "fresh_evaluation_receipt_readback",
            "allocation_and_lease_execution_evidence",
        ],
    }


def rank_repeatable(samples: list[dict]) -> dict:
    """Rank already qualified samples; caller must verify ordered independent receipts."""
    require(
        isinstance(samples, list) and bool(samples), "missing repeatable candidates"
    )
    candidates, units, fingerprints = {}, set(), set()
    for sample in samples:
        workers = sample["workers"]
        rates = sample["rates"]
        require(
            integer(workers, 1) and workers not in candidates,
            "duplicate or invalid worker count",
        )
        require(
            isinstance(rates, list)
            and len(rates) >= 2
            and all(number(r) and r > 0 for r in rates),
            "two positive repeated rates required",
        )
        require(
            sample.get("qualified") is True,
            "unqualified candidate cannot enter ranking",
        )
        require(
            isinstance(sample.get("unit"), str)
            and bool(sample["unit"])
            and isinstance(sample.get("fixed_inputs_sha256"), str)
            and bool(sample["fixed_inputs_sha256"]),
            "ranking lacks common units or fixed inputs",
        )
        units.add(sample["unit"])
        fingerprints.add(sample["fixed_inputs_sha256"])
        # A single unusually fast repetition cannot establish repeatable throughput.
        candidates[workers] = min(rates)
    require(
        len(units) == len(fingerprints) == 1, "incomparable candidate units or inputs"
    )
    fastest = max(candidates.values())
    selected = min(n for n, rate in candidates.items() if rate >= 0.95 * fastest)
    return {
        "decision": "ranking_only",
        "workers": selected,
        "repeatable_rate": candidates[selected],
        "fastest_repeatable_rate": fastest,
        "selection_tolerance": 0.05,
    }
