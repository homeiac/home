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
    assert result["candidate_review"]["decision"] == "eligible"
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
    result = qualify(session, receipt, comparison, NOW + 2 * WINDOW)["candidate_review"]
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
        qualify(session, receipt, comparison, NOW + WINDOW)["candidate_review"][
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
        qualify(session, receipt, comparison, warmed + WINDOW)["candidate_review"][
            "decision"
        ]
        == "eligible"
    )
    comparison["trial"]["admitted_ns"] = NOW + 2 * 10**9
    comparison["trial"]["warmup_start_ns"] = NOW + 2 * 10**9
    with pytest.raises(ValueError, match="first candidate"):
        qualify(session, receipt, comparison, warmed + WINDOW)


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
