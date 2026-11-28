"""New workload names and observer mappings use the same safety policy."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

PERF = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PERF))
from shared_workloads import shared_context
from test_shared_workloads import CRICKET, WINDOW, window


def neutral(name: str) -> dict:
    value = window()
    value["topology"] = json.loads((PERF / "shared-workloads.json").read_text())
    return json.loads(json.dumps(value).replace(CRICKET, name))


@pytest.mark.parametrize("name", ["cricket-indexer", "speech-transcription", "document-index"])
def test_safety_requirements_do_not_depend_on_workload_name(name: str) -> None:
    value = neutral(name)
    assert shared_context(value, 3 * WINDOW)["decision"] == "eligible"
    value["comparison"]["trial"]["max_sample_gap_s"] = 16
    assert shared_context(value, 3 * WINDOW)["decision"] == "hold"
    value = neutral(name)
    value["comparison"]["trial"]["workloads"][name]["p95_s"] = 2.3
    assert shared_context(value, 3 * WINDOW)["decision"] == "rollback"
    value = neutral(name)
    value["comparison"]["trial"]["workloads"]["immich-pet-tagger"].pop("activity")
    assert shared_context(value, 3 * WINDOW)["decision"] == "hold"


def test_observer_registry_plugs_in_a_new_workload_and_replays_offline(tmp_path: Path) -> None:
    path = PERF / "observe-shared-workloads.py"
    spec = importlib.util.spec_from_file_location("plugin_observer", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"version": 1, "workloads": {"new-worker": {
        "heartbeat": ["new_updated_seconds", 'stage="embed"'],
        "pending": ["new_items", 'state="pending"']}}}))
    response = {"status": "success", "data": {"result": [
        {"metric": {"__name__": "new_updated_seconds", "stage": "embed"}, "value": [1000, "999"]},
        {"metric": {"__name__": "new_items", "state": "pending"}, "value": [1000, "0"]}]}}
    source = tmp_path / "response.json"
    source.write_text(json.dumps(response))
    command = [sys.executable, str(path), "--registry", str(registry), "--input", str(source), "--at", "1000"]
    a = subprocess.check_output(command)
    assert subprocess.check_output(command) == a
    assert json.loads(a)["workloads"]["new-worker"]["observations"] == {"pending": 0}
    registry.write_text(registry.read_text().replace("new_items", 'new_items|injected'))
    with pytest.raises(ValueError, match="metric"):
        module.registry(registry)


def test_service_target_uses_its_real_slo_objective_without_fabricated_outputs() -> None:
    from test_service_budgets import service_comparison
    value = service_comparison()
    comparison = value["comparison"]
    comparison["subject"] = "frigate"
    comparison["service_objective"] = {"metric": "inference_p95", "contract_ref": "fixture/service-slo"}
    comparison["trial"]["workloads"]["frigate"]["service_metrics"]["inference_p95"]["value"] = .8
    result = shared_context(value, 3 * WINDOW)
    assert result["decision"] == "eligible"
    assert result["service_objective_change_percent"] == {"frigate": 20}
    assert "frigate" not in result["verified_change_percent"]
    assert "verified" not in comparison["trial"]["workloads"]["frigate"]
