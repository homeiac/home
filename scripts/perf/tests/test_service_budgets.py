"""Service-only peers require measured budgets, and unobserved queues cannot claim idle."""

import json
from pathlib import Path

import pytest
from shared_workloads import shared_context
from test_shared_workloads import KI, METAL, PET, WINDOW, window


def service_comparison() -> dict:
    """Synthetic placement for testing; it does not change the real Frigate route."""
    sample = window()
    topology = json.loads(
        (Path(__file__).resolve().parents[1] / "shared-workloads.json").read_text()
    )
    topology[METAL]["workloads"].append("frigate")
    topology[METAL]["measurement_kinds"] = {"frigate": "service"}
    sample["topology"] = topology
    comparison = sample["comparison"]
    comparison["service_budgets"] = {
        "frigate": {
            "inference_p95": {
                "unit": "s",
                "direction": "lower",
                "max": 2,
                "max_regression": 0.1,
            },
            "camera_fps": {
                "unit": "frame/s",
                "direction": "higher",
                "min": 4,
                "max_regression": 0.1,
            },
        }
    }
    for phase in ("baseline", "trial"):
        row = comparison[phase]
        row["callers"][METAL].append("frigate")
        row["workloads"]["frigate"] = {
            "demand": True,
            "baseline_preserved": True,
            "cohort": "same-camera-streams",
            "quality_ok": True,
            "slo_ok": True,
            "service_metrics": {
                name: {
                    "unit": unit,
                    "value": value,
                    "samples": 21,
                    "source_age_s": 0,
                    "evidence_ref": "fixture/service",
                }
                for name, unit, value in (
                    ("inference_p95", "s", 1),
                    ("camera_fps", "frame/s", 5),
                )
            },
        }
    return sample


def test_service_does_not_need_fabricated_durable_completions() -> None:
    result = shared_context(service_comparison(), 3 * WINDOW)
    assert result["decision"] == "eligible"
    assert "frigate" in result["affected"]
    assert "frigate" not in result["verified_change_percent"]


@pytest.mark.parametrize(
    "field,value,expected",
    [
        ("value", 1.2, "rollback"),
        ("samples", 20, "hold"),
        ("source_age_s", 16, "hold"),
        ("evidence_ref", "", "hold"),
        ("unit", "ms", "hold"),
        ("value", None, "hold"),
    ],
)
def test_service_loss_or_missing_observation_prevents_win(
    field: str, value: object, expected: str
) -> None:
    sample = service_comparison()
    sample["comparison"]["trial"]["workloads"]["frigate"]["service_metrics"][
        "inference_p95"
    ][field] = value
    assert shared_context(sample, 3 * WINDOW)["decision"] == expected


def test_missing_budget_and_already_bad_baseline_hold() -> None:
    sample = service_comparison()
    sample["comparison"]["service_budgets"] = {}
    assert shared_context(sample, 3 * WINDOW)["decision"] == "hold"
    sample = service_comparison()
    sample["comparison"]["baseline"]["workloads"]["frigate"]["service_metrics"][
        "inference_p95"
    ]["value"] = 3
    assert shared_context(sample, 3 * WINDOW)["decision"] == "hold"


def test_loosening_relative_budget_or_relabelling_indexer_cannot_bypass_gates() -> None:
    sample = service_comparison()
    sample["comparison"]["service_budgets"]["frigate"]["inference_p95"][
        "max_regression"
    ] = 0.5
    assert shared_context(sample, 3 * WINDOW)["decision"] == "hold"
    sample = service_comparison()
    for phase in ("baseline", "trial"):
        row = sample["comparison"][phase]["workloads"][KI]
        row["measurement_kind"] = "service"
        del row["completed_items"]
    assert shared_context(sample, 3 * WINDOW)["decision"] == "hold"


@pytest.mark.parametrize(
    "mutation", ["absent", "stale", "reservation", "queued", "unknown"]
)
def test_idle_peers_require_fresh_queue_and_reservation_evidence(mutation: str) -> None:
    sample = window()
    row = sample["comparison"]["trial"]["workloads"][PET]
    if mutation == "absent":
        del row["activity"]
    elif mutation == "stale":
        row["activity"]["observed_ns"] -= 16 * 10**9
    elif mutation == "reservation":
        del row["activity"]["reservation_workers"]
    elif mutation == "queued":
        row["activity"]["runnable"] = 1
    else:
        row["activity"]["state"] = "unobserved"
    assert shared_context(sample, 3 * WINDOW)["decision"] == "hold"


def test_frigate_route_is_registered_as_service_and_conflicts_hold() -> None:
    sample = service_comparison()
    assert (
        sample["topology"]["pumped-piglet/rtx3070"]["measurement_kinds"]["frigate"]
        == "service"
    )
    sample["topology"]["mac-m5/bonsai-slots"]["workloads"].append("frigate")
    assert shared_context(sample, 3 * WINDOW)["decision"] == "hold"
