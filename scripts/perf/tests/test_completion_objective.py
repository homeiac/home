"""Production finish time excludes evaluation work and cannot bypass readback."""

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from completion_objective import project

SECOND = 10**9
CUTOFF = 601 * SECOND


def objective() -> dict:
    def phase(start, gpu, cpu):
        return {"start_ns": start * SECOND, "end_ns": (start + 300) * SECOND,
                "unique_production_completed": gpu + cpu,
                "verified_production_completed": gpu + cpu,
                "backend_unique_production_completed": {"gpu": gpu, "cpu": cpu},
                "backend_verified_production_completed": {"gpu": gpu, "cpu": cpu},
                "evaluation_completed": 10000, "readback_ref": "fixture/native-reader",
                "evidence_ref": "fixture/unique-output-export"}
    return {"version": 1, "workload": "document-index", "unit": "document_versions",
            "remaining": {"amount": 24305, "observed_ns": CUTOFF,
                          "evidence_ref": "fixture/queue-snapshot"},
            "increment_backends": ["cpu"], "baseline": phase(1, 150, 0),
            "trial": phase(301, 150, 15)}


def test_whole_remaining_time_uses_combined_production_not_replay() -> None:
    report = project(objective(), CUTOFF)
    assert report["decision"] == "evidence_ready_not_admitted"
    assert report["phases"]["baseline"]["projected_remaining_s"] == 48610
    assert report["phases"]["trial"]["combined_production_per_s"] == .55
    assert report["projected_finish_improvement_percent"] == pytest.approx(100 / 11)
    assert report["projected_finish_delta_s"] < 0
    assert "not established" in report["causal_bottleneck"]


def test_diagnostic_eta_cannot_promote_missing_publication() -> None:
    row = objective()
    for phase in ("baseline", "trial"):
        row[phase].update(verified_production_completed=None,
                          backend_verified_production_completed=None, readback_ref=None)
    result = project(row, CUTOFF)
    assert result["projected_finish_delta_s"] < 0
    assert result["decision"] == "hold"
    assert any("cpu:" in r for r in result["reasons"])


def test_replay_only_and_gpu_gain_without_cpu_contribution_do_not_qualify() -> None:
    row = objective()
    row["trial"].update(unique_production_completed=165, verified_production_completed=165,
                        backend_unique_production_completed={"gpu": 165, "cpu": 0},
                        backend_verified_production_completed={"gpu": 165, "cpu": 0})
    assert project(row, CUTOFF)["decision"] == "hold"
    row["trial"] = deepcopy(row["baseline"])
    row["trial"].update(start_ns=301 * SECOND, end_ns=CUTOFF)
    assert project(row, CUTOFF)["projected_finish_delta_s"] == 0


@pytest.mark.parametrize("mutate", [
    lambda x: x["trial"].update(unique_production_completed=999),
    lambda x: x["trial"].update(verified_production_completed=166),
    lambda x: x["trial"].update(evaluation_completed=True),
    lambda x: x["trial"].update(start_ns=300 * SECOND),
    lambda x: x["remaining"].update(observed_ns=CUTOFF + 1),
    lambda x: x["remaining"].update(amount=float("nan")),
])
def test_inconsistent_or_future_receipts_fail(mutate) -> None:
    row = objective()
    mutate(row)
    with pytest.raises(ValueError):
        project(row, CUTOFF)


def test_cli_replay_is_byte_identical_without_live_sampling(tmp_path: Path) -> None:
    path = tmp_path / "objective.json"
    path.write_text(json.dumps(objective()))
    command = [sys.executable, str(Path(__file__).resolve().parents[1] / "completion_objective.py"),
               str(path), "--at-ns", str(CUTOFF)]
    first = subprocess.check_output(command)
    assert subprocess.check_output(command) == first
    assert json.loads(first)["decision"] == "evidence_ready_not_admitted"


def test_missing_objective_holds() -> None:
    assert project(None, CUTOFF)["decision"] == "hold"
