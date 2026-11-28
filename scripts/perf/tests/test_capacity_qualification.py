"""Capacity safety qualification does not conflate slower candidates with peer loss."""

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from capacity_qualification import context, qualify, rank_repeatable
from capacity_trials import register
from otel_diagnosis import digest
from shared_workloads import shared_context
from test_capacity_trials import DEVICE, NOW, PEER, POOL, TARGET, fixture

WINDOW = 300 * 10**9


def sample(tmp_path: Path) -> tuple[dict, dict, dict]:
    session, spec = fixture()
    target = {
        "demand": False,
        "verified": 0,
        "completed_items": 0,
        "unit": "reviewed-source-minutes",
        "cohort": spec["fixed_inputs"]["cohort_sha256"],
        "quality_ok": True,
        "slo_ok": True,
        "baseline_preserved": True,
        "activity": {
            "state": "idle",
            "runnable": 0,
            "reservation_workers": 0,
            "observed_ns": NOW,
            "evidence_ref": "fixture/empty-queue",
        },
    }
    peer = {
        "demand": True,
        "verified": 100,
        "completed_items": 10,
        "unit": "faces",
        "cohort": "fixed-faces",
        "quality_ok": True,
        "slo_ok": True,
        "baseline_preserved": True,
        "p95_s": 2,
        "terminal_error_rate": 0,
    }
    before = {
        "start_ns": NOW - WINDOW,
        "end_ns": NOW,
        "warmed": True,
        "max_sample_gap_s": 15,
        "environment": spec["fixed_inputs"]["environment_sha256"],
        "allocation": {TARGET: 0, PEER: 4},
        "callers": {POOL: [PEER], DEVICE: [PEER]},
        "workloads": {TARGET: target, PEER: peer},
    }
    trial = deepcopy(before)
    trial.update(
        start_ns=NOW,
        end_ns=NOW + WINDOW,
        admitted_ns=NOW,
        warmup_start_ns=NOW,
        warmup_end_ns=NOW,
        allocation={TARGET: 4, PEER: 4},
        callers={POOL: [TARGET, PEER], DEVICE: [TARGET, PEER]},
    )
    trial["workloads"][TARGET].update(
        demand=True,
        verified=100,
        completed_items=10,
        fresh_inference_items=10,
        terminal_error_rate=0,
        p95_s=2,
    )
    spec["peer_baseline_sha256"] = digest(before)
    register(session, spec, NOW, tmp_path / "receipt")
    receipt = json.loads((tmp_path / "receipt").read_text())
    comparison = {
        "action": spec["action"],
        "subject": TARGET,
        "resources": [POOL],
        "capacity_registration_sha256": receipt["receipt_sha256"],
        "fixed_inputs": spec["fixed_inputs"],
        "output_accounting": spec["output_accounting"],
        "min_gain": 0,
        "max_peer_loss": 0.10,
        "baseline": before,
        "peer_baseline": deepcopy(before),
        "trial": trial,
    }
    return session, receipt, comparison


def test_idle_target_qualifies_without_fabricated_baseline_completions(
    tmp_path: Path,
) -> None:
    session, receipt, comparison = sample(tmp_path)
    result = qualify(session, receipt, comparison, NOW + WINDOW)
    assert result["decision"] == "not_admitted"
    assert result["capacity_budget_review"]["decision"] == "eligible"
    assert result["candidate_review"]["decision"] == "hold"
    assert result["completion_review"]["decision"] == "hold"
    assert not result["proceed"]
    assert TARGET not in result["candidate_review"]["verified_change_percent"]
    assert "fresh_evaluation_receipt_readback" in result["pending"]
    # An untrusted JSON flag cannot opt ordinary reviews into the special baseline.
    comparison["baseline_mode"] = "observed_idle"
    assert (
        shared_context(
            {"topology": session["topology"], "comparison": comparison}, NOW + WINDOW
        )["decision"]
        == "hold"
    )


@pytest.mark.parametrize(
    "field,value,decision",
    [
        ("verified", 89, "rollback"),
        ("p95_s", 2.21, "rollback"),
        ("terminal_error_rate", 0.01, "rollback"),
        ("completed_items", 9, "hold"),
        ("quality_ok", False, "rollback"),
        ("baseline_preserved", False, "rollback"),
    ],
)
def test_idle_target_cannot_hide_peer_loss(
    tmp_path: Path, field: str, value: object, decision: str
) -> None:
    session, receipt, comparison = sample(tmp_path)
    comparison["trial"]["workloads"][PEER][field] = value
    assert (
        qualify(session, receipt, comparison, NOW + WINDOW)["candidate_review"][
            "decision"
        ]
        == decision
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda c: c["baseline"]["workloads"][TARGET].update(
            verified=10, completed_items=10
        ),
        lambda c: c["baseline"]["workloads"][TARGET]["activity"].update(
            observed_ns=NOW - 16 * 10**9
        ),
        lambda c: c["baseline"]["workloads"][TARGET]["activity"].update(
            reservation_workers=1
        ),
        lambda c: c["trial"]["workloads"][TARGET].update(fresh_inference_items=9),
        lambda c: c["trial"]["workloads"][TARGET].update(verified=0),
    ],
)
def test_fake_idle_and_cached_outputs_hold(tmp_path: Path, mutation) -> None:
    session, receipt, comparison = sample(tmp_path)
    mutation(comparison)
    if digest(comparison["baseline"]) != receipt["spec"]["peer_baseline_sha256"]:
        with pytest.raises(ValueError, match="changed the protected baseline"):
            qualify(session, receipt, comparison, NOW + WINDOW)
        return
    assert (
        qualify(session, receipt, comparison, NOW + WINDOW)["candidate_review"][
            "decision"
        ]
        == "hold"
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda c: c["trial"]["allocation"].update(photo=3),
        lambda c: c["trial"]["allocation"].update(**{TARGET: 5}),
        lambda c: c["fixed_inputs"].update(model_sha256="c" * 64),
        lambda c: c["trial"]["callers"][DEVICE].append("new-peer"),
        lambda c: c.update(max_peer_loss=0.11),
        lambda c: c.update(min_gain=0.05),
        lambda c: c.update(service_budgets={PEER: {"changed": "after-registration"}}),
        lambda c: c.update(capacity_registration_sha256="b" * 64),
        lambda c: c["trial"]["allocation"].update(**{TARGET: 3}),
        lambda c: c["trial"].update(admitted_ns=NOW + 20 * 10**9),
        lambda c: c["trial"].update(end_ns=NOW + 4000 * 10**9),
    ],
)
def test_changed_scope_or_allocations_fail_before_special_target_handling(
    tmp_path: Path, mutation
) -> None:
    session, receipt, comparison = sample(tmp_path)
    mutation(comparison)
    with pytest.raises(ValueError):
        qualify(session, receipt, comparison, NOW + WINDOW)


def test_lower_rate_can_qualify_and_mutation_cannot_reuse_context(
    tmp_path: Path,
) -> None:
    session, receipt, comparison = sample(tmp_path)
    comparison["baseline"] = deepcopy(comparison["trial"])
    comparison["trial"].update(
        start_ns=NOW + WINDOW,
        end_ns=NOW + 2 * WINDOW,
        admitted_ns=NOW + WINDOW,
        warmup_start_ns=NOW + WINDOW,
        warmup_end_ns=NOW + WINDOW,
    )
    comparison["trial"]["allocation"][TARGET] = 2
    comparison["trial"]["workloads"][TARGET]["verified"] = 97
    result = qualify(session, receipt, comparison, NOW + 2 * WINDOW)["capacity_budget_review"]
    assert result["decision"] == "eligible"
    assert result["verified_change_percent"][TARGET] == -3
    validated = context(session, receipt, comparison)
    comparison["trial"]["workloads"][PEER]["verified"] = 1
    with pytest.raises(ValueError, match="changed after validation"):
        shared_context(
            {"topology": session["topology"], "comparison": comparison},
            NOW + 2 * WINDOW,
            capacity=validated,
        )


def test_tighter_registered_latency_budget_stays_binding(tmp_path: Path) -> None:
    session, spec = fixture()
    _, _, comparison = sample(tmp_path)
    spec["peer_baseline_sha256"] = digest(comparison["peer_baseline"])
    spec["limits"]["max_peer_p95_growth"] = 0.01
    register(session, spec, NOW, tmp_path / "tight")
    tight = json.loads((tmp_path / "tight").read_text())
    comparison["capacity_registration_sha256"] = tight["receipt_sha256"]
    comparison["trial"]["workloads"][PEER]["p95_s"] = 2.04
    assert (
        qualify(session, tight, comparison, NOW + WINDOW)["candidate_review"][
            "decision"
        ]
        == "rollback"
    )


@pytest.mark.parametrize(
    "value,decision", [(None, "hold"), (2, "eligible"), (2.3, "rollback")]
)
def test_service_peer_budgets_remain_binding(
    tmp_path: Path, value: float | None, decision: str
) -> None:
    session, spec = fixture()
    _, _, comparison = sample(tmp_path)
    spec["peer_baseline_sha256"] = digest(comparison["peer_baseline"])
    for route in session["topology"].values():
        route["measurement_kinds"] = {PEER: "service"}
    spec["service_budgets"] = {
        PEER: {
            "latency": {
                "unit": "ms",
                "direction": "lower",
                "max_regression": 0.1,
                "max": 3,
            }
        }
    }
    register(session, spec, NOW, tmp_path / "service")
    receipt = json.loads((tmp_path / "service").read_text())
    comparison["capacity_registration_sha256"] = receipt["receipt_sha256"]
    comparison["service_budgets"] = spec["service_budgets"]
    if value is not None:
        for name, measured in (("baseline", 2), ("trial", value)):
            comparison[name]["workloads"][PEER]["service_metrics"] = {
                "latency": {
                    "unit": "ms",
                    "value": measured,
                    "samples": 21,
                    "source_age_s": 0,
                    "evidence_ref": "fixture/service",
                }
            }
        # Baseline service measurements are sealed before registration too.
        comparison["peer_baseline"] = deepcopy(comparison["baseline"])
        spec["peer_baseline_sha256"] = digest(comparison["peer_baseline"])
        register(session, spec, NOW, tmp_path / "service-measured")
        receipt = json.loads((tmp_path / "service-measured").read_text())
        comparison["capacity_registration_sha256"] = receipt["receipt_sha256"]
    assert (
        qualify(session, receipt, comparison, NOW + WINDOW)["capacity_budget_review"][
            "decision"
        ]
        == decision
    )


@pytest.mark.parametrize(
    "metric,previous,current",
    [
        ("verified", 90, 81),
        ("p95_s", 2.2, 2.42),
    ],
)
def test_pairwise_losses_cannot_compound_beyond_original_baseline(
    tmp_path: Path, metric: str, previous: float, current: float
) -> None:
    session, receipt, comparison = sample(tmp_path)
    comparison["baseline"] = deepcopy(comparison["trial"])
    comparison["baseline"]["workloads"][PEER][metric] = previous
    comparison["trial"].update(
        start_ns=NOW + WINDOW,
        end_ns=NOW + 2 * WINDOW,
        admitted_ns=NOW + WINDOW,
        warmup_start_ns=NOW + WINDOW,
        warmup_end_ns=NOW + WINDOW,
    )
    comparison["trial"]["allocation"][TARGET] = 3
    comparison["trial"]["workloads"][PEER][metric] = current
    paired = shared_context(
        {"topology": session["topology"], "comparison": comparison},
        NOW + 2 * WINDOW,
        capacity=context(session, receipt, comparison),
    )
    assert paired["decision"] == "eligible"
    result = qualify(session, receipt, comparison, NOW + 2 * WINDOW)
    assert result["candidate_review"]["decision"] == "rollback"
    assert result["protected_baseline_review"]["decision"] == "rollback"


def test_delayed_warmup_is_separate_from_fresh_admission(tmp_path: Path) -> None:
    session, receipt, comparison = sample(tmp_path)
    warmed = NOW + 30 * 10**9
    comparison["trial"].update(
        warmup_end_ns=warmed, start_ns=warmed, end_ns=warmed + WINDOW
    )
    assert (
        qualify(session, receipt, comparison, warmed + WINDOW)["capacity_budget_review"][
            "decision"
        ]
        == "eligible"
    )
    comparison["trial"]["admitted_ns"] = NOW + 2 * 10**9
    comparison["trial"]["warmup_start_ns"] = NOW + 2 * 10**9
    with pytest.raises(ValueError, match="first candidate"):
        qualify(session, receipt, comparison, warmed + WINDOW)


def test_completion_objective_controls_candidate_not_only_peer_budgets(tmp_path: Path) -> None:
    from native_output import AccountingProof

    session, receipt, comparison = sample(tmp_path)
    comparison["baseline"] = deepcopy(comparison["trial"])
    comparison["trial"].update(start_ns=NOW + WINDOW, end_ns=NOW + 2 * WINDOW,
                               admitted_ns=NOW + WINDOW, warmup_start_ns=NOW + WINDOW,
                               warmup_end_ns=NOW + WINDOW)
    comparison["trial"]["allocation"][TARGET] = 2
    comparison["trial"]["workloads"][TARGET]["verified"] = 120
    phases = {}
    for name, cpu in (("baseline", 0), ("trial", 20)):
        phases[name] = {k: comparison[name][k] for k in ("start_ns", "end_ns")}
        phases[name].update(unique_production_completed=100 + cpu,
                            verified_production_completed=100 + cpu,
                            backend_unique_production_completed={"gpu": 100, "cpu": cpu},
                            backend_verified_production_completed={"gpu": 100, "cpu": cpu},
                            evaluation_completed=10000, readback_ref="fixture/native-reader",
                            evidence_ref="fixture/native-output")
    comparison["completion_objective"] = {
        "version": 1, "workload": TARGET, "unit": "reviewed-source-minutes",
        "increment_backends": ["cpu"],
        "remaining": {"amount": 1000, "observed_ns": NOW,
                      "evidence_ref": "fixture/fixed-remaining"}, **phases}
    spec = deepcopy(receipt["spec"])
    spec["increment_backends"] = ["cpu"]
    register(session, spec, NOW, tmp_path / "objective-bound")
    receipt = json.loads((tmp_path / "objective-bound").read_text())
    comparison["capacity_registration_sha256"] = receipt["receipt_sha256"]
    proofs = {name: AccountingProof(TARGET, "fixture", "reviewed-source-minutes",
                                    phases[name]["start_ns"], phases[name]["end_ns"],
                                    phases[name]["verified_production_completed"],
                                    tuple(phases[name]["backend_verified_production_completed"].items()),
                                    "f" * 64, digest(session)) for name in ("baseline", "trial")}
    assert qualify(session, receipt, comparison, NOW + 2 * WINDOW)["candidate_review"]["decision"] == "hold"
    valid = qualify(session, receipt, comparison, NOW + 2 * WINDOW, proofs)
    assert valid["candidate_review"]["decision"] == "eligible"
    assert valid["completion_review"]["projected_finish_delta_s"] < 0
    assert valid["decision"] == "not_admitted" and not valid["proceed"]
    bad_latency = deepcopy(comparison)
    bad_latency["trial"]["workloads"][TARGET]["p95_s"] = 3
    assert qualify(session, receipt, bad_latency, NOW + 2 * WINDOW, proofs)["candidate_review"]["decision"] == "rollback"
    spoofed = deepcopy(comparison)
    spoofed["completion_objective"]["trial"]["backend_verified_production_completed"] = {"gpu": 120, "cpu": 0}
    spoofed["completion_objective"]["trial"]["backend_unique_production_completed"] = {"gpu": 120, "cpu": 0}
    with pytest.raises(ValueError, match="backend contribution"):
        qualify(session, receipt, spoofed, NOW + 2 * WINDOW, proofs)
    # A faster replay or GPU rate cannot substitute for production CPU readback.
    comparison["completion_objective"]["trial"].update(
        verified_production_completed=None, backend_verified_production_completed=None,
        readback_ref=None)
    missing = qualify(session, receipt, comparison, NOW + 2 * WINDOW)
    assert missing["capacity_budget_review"]["decision"] == "eligible"
    assert missing["candidate_review"]["decision"] == "hold"
    assert "verified_production_completion_objective" in missing["pending"]
    comparison["trial"]["workloads"][PEER]["p95_s"] = 3
    assert qualify(session, receipt, comparison, NOW + 2 * WINDOW)["candidate_review"]["decision"] == "rollback"


def test_idle_target_still_requires_measured_latency(tmp_path: Path) -> None:
    session, receipt, comparison = sample(tmp_path)
    comparison["trial"]["workloads"][TARGET].pop("p95_s")
    result = qualify(session, receipt, comparison, NOW + WINDOW)
    assert result["capacity_budget_review"]["decision"] == "hold"


def test_zero_increment_control_can_win_five_percent_ranking() -> None:
    samples = [{"workers": workers, "rates": [rate, rate], "qualified": True,
                "unit": "faces/min", "fixed_inputs_sha256": "a" * 64}
               for workers, rate in ((0, 30), (1, 31))]
    assert rank_repeatable(samples)["workers"] == 0


def test_descending_candidate_can_use_protected_completion_control(tmp_path: Path) -> None:
    from native_output import AccountingProof
    session, old, comparison = sample(tmp_path)
    spec = deepcopy(old["spec"])
    original = comparison["peer_baseline"]
    original["allocation"][TARGET] = 1
    original["workloads"][TARGET].update(demand=True, verified=100, fresh_inference_items=10,
                                         completed_items=10, terminal_error_rate=0, p95_s=2)
    original["workloads"][TARGET].pop("activity")
    for names in original["callers"].values():
        names.append(TARGET)
    for key in ("baseline_allocation", "protected_allocation", "rollback_allocation"):
        spec[key][TARGET] = 1
    for row in spec["constraints"]:
        row["reserved"][TARGET], row["capacity"] = 1, 9
    spec.update(baseline_mode="active", candidates=[5, 4, 3, 2], increment_backends=["cpu"],
                peer_baseline_sha256=digest(original))
    register(session, spec, NOW, tmp_path / "active")
    receipt = json.loads((tmp_path / "active").read_text())
    comparison["capacity_registration_sha256"] = receipt["receipt_sha256"]
    for name, workers, amount, start in (("baseline", 5, 130, NOW), ("trial", 2, 125, NOW + WINDOW)):
        comparison[name] = deepcopy(original)
        comparison[name].update(start_ns=start, end_ns=start + WINDOW, admitted_ns=start,
                                warmup_start_ns=start, warmup_end_ns=start)
        comparison[name]["allocation"][TARGET] = workers
        comparison[name]["workloads"][TARGET]["verified"] = amount
    phases, proofs = {}, {}
    for name, phase, cpu in (("baseline", original, 0), ("trial", comparison["trial"], 25)):
        phases[name] = {k: phase[k] for k in ("start_ns", "end_ns")}
        phases[name].update(unique_production_completed=100 + cpu, verified_production_completed=100 + cpu,
                            backend_unique_production_completed={"gpu": 100, "cpu": cpu},
                            backend_verified_production_completed={"gpu": 100, "cpu": cpu},
                            evaluation_completed=0, readback_ref="fixture/native-reader", evidence_ref="fixture/production")
        proofs[name] = AccountingProof(TARGET, "fixture", "reviewed-source-minutes", phase["start_ns"],
                                       phase["end_ns"], 100 + cpu, (("gpu", 100), ("cpu", cpu)),
                                       "f" * 64, digest(session))
    comparison["completion_objective"] = {"version": 1, "baseline_scope": "protected", "workload": TARGET,
        "unit": "reviewed-source-minutes", "increment_backends": ["cpu"],
        "remaining": {"amount": 1000, "observed_ns": NOW, "evidence_ref": "fixture/queue"}, **phases}
    result = qualify(session, receipt, comparison, NOW + 2 * WINDOW, proofs)
    assert result["candidate_review"]["decision"] == "eligible"
    assert result["candidate_review"]["verified_change_percent"][TARGET] < 0  # Below previous fastest.
    assert result["completion_review"]["projected_finish_delta_s"] < 0  # Still beats protected control.
    assert not result["proceed"]


def test_original_baseline_cannot_be_replaced_mid_sweep(tmp_path: Path) -> None:
    session, receipt, comparison = sample(tmp_path)
    comparison["peer_baseline"]["workloads"][PEER]["verified"] = 80
    with pytest.raises(ValueError, match="original protected baseline"):
        qualify(session, receipt, comparison, NOW + WINDOW)


def rankings() -> list[dict]:
    return [
        {
            "workers": workers,
            "rates": rates,
            "unit": "minutes/s",
            "qualified": True,
            "fixed_inputs_sha256": "a" * 64,
        }
        for workers, rates in [
            (4, [100, 101]),
            (3, [98, 99]),
            (2, [97, 98]),
            (1, [94, 95]),
        ]
    ]


def test_fewest_workers_within_five_percent_of_repeatable_best() -> None:
    result = rank_repeatable(rankings())
    assert result["decision"] == "ranking_only"
    assert result["workers"] == 2
    assert result["fastest_repeatable_rate"] == 100


@pytest.mark.parametrize(
    "field,value",
    [
        ("rates", [100]),
        ("rates", [float("nan"), 100]),
        ("rates", [0, 100]),
        ("qualified", False),
        ("unit", "other"),
        ("fixed_inputs_sha256", "different"),
    ],
)
def test_incomplete_or_incomparable_repetitions_cannot_rank(
    field: str, value: object
) -> None:
    rows = rankings()
    rows[0][field] = value
    with pytest.raises(ValueError):
        rank_repeatable(rows)
