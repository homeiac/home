"""Fleet decisions protect declared and dynamically observed resource clients."""
import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

PERF = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PERF))
from shared_workloads import shared_context

SLOTS = "mac-m5/bonsai-slots"
METAL = "mac-m5/metal"
WINDOW = 300 * 10**9
CRICKET, KI, PET = "cricket-indexer", "knowledge-index", "immich-pet-tagger"


def window():
    def row(count, unit):
        return dict(demand=True, verified=count, unit=unit, cohort="matched-replay",
                    completed_items=10, p95_s=2, terminal_error_rate=0, quality_ok=True, slo_ok=True, baseline_preserved=True)
    baseline = dict(start_ns=WINDOW, end_ns=2*WINDOW, warmed=True, max_sample_gap_s=15, environment="fixed-models-and-worker-floors",
                    callers={SLOTS: [CRICKET, KI], METAL: [CRICKET, KI]},
                    workloads={CRICKET: row(10, "reviewed source minutes"), KI: row(35, "verified captions"),
                               PET: dict(demand=False, baseline_preserved=True,
                                         activity=dict(state="idle", runnable=0, reservation_workers=0,
                                                       observed_ns=2*WINDOW, evidence_ref="fixture/idle"))})
    trial = deepcopy(baseline)
    trial.update(start_ns=2*WINDOW, end_ns=3*WINDOW)
    trial["workloads"][PET]["activity"]["observed_ns"] = 3*WINDOW
    trial["workloads"][CRICKET]["verified"] = 12
    return {"comparison": dict(resources=[SLOTS], subject=CRICKET, baseline=baseline, trial=trial,
                               min_gain=0.05, max_peer_loss=0.0)}


def test_shared_server_and_device_dependencies():
    decision = shared_context(window(), 3*WINDOW)
    assert decision["decision"] == "eligible"
    assert decision["resources"] == sorted([SLOTS, METAL])
    assert decision["affected"] == sorted([KI, CRICKET, PET])
    assert decision["verified_change_percent"] == {CRICKET: 20.0, KI: 0.0}


@pytest.mark.parametrize("field,value,decision", [
    ("completed_items", 9, "hold"), ("p95_s", 2.3, "rollback"), ("terminal_error_rate", .01, "rollback"),
    ("verified", 30, "rollback"), ("quality_ok", False, "rollback"),
    ("slo_ok", False, "rollback"), ("baseline_preserved", False, "rollback"),
    ("cohort", "different", "hold"), ("quality_ok", None, "hold"), ("demand", False, "hold")])
def test_even_a_faster_subject_cannot_hide_a_peer_loss(field, value, decision):
    sample = window()
    sample["comparison"]["trial"]["workloads"][KI][field] = value
    assert shared_context(sample, 3*WINDOW)["decision"] == decision


def test_unknown_client_missing_census_and_staleness():
    sample = window()
    assert shared_context(sample, 5*WINDOW)["decision"] == "hold"
    trial = sample["comparison"]["trial"]
    trial["callers"][METAL].append("unregistered-service")
    decision = shared_context(sample, 3*WINDOW)
    assert decision["decision"] == "hold" and "unregistered-service" in decision["affected"]
    del trial["callers"][METAL]
    assert shared_context(sample, 3*WINDOW)["decision"] == "hold"
    del trial["workloads"][KI]
    assert shared_context(sample, 3*WINDOW)["decision"] == "hold"


def test_peer_activity_uses_cutoff_and_original_source_age(tmp_path):
    path = tmp_path / "activity.json"
    path.write_text(json.dumps(dict(as_of_unix_s=1000, workloads={
        KI: dict(source_age_s=170, fresh=True, observations={"saved": 0}),
        CRICKET: dict(source_age_s=10, fresh=True, observations={"mac_active_workers": 4})})))
    checkpoint = dict(activity_capture=str(path))
    current = shared_context(checkpoint, 1020 * 10**9)
    assert current["caller_observations"] == {KI: None, CRICKET: {"mac_active_workers": 4}}
    assert current["decision"] == "observe_only"
    assert "caller_observations" not in shared_context(checkpoint, 999 * 10**9)


def test_live_observer_distinguishes_absent_stale_zero_and_desired(monkeypatch):
    spec = importlib.util.spec_from_file_location("observe", PERF / "observe-shared-workloads.py")
    observer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(observer)
    def result(name, value, **labels):
        return dict(metric=dict(__name__=name, **labels), value=[1000, str(value)])
    rows = [result("cricket_heartbeat_timestamp_seconds", 999),
            result("cricket_workers", 4, backend="mac", kind="desired"),
            result("cricket_workers", 0, backend="mac", kind="active"),
            result("cricket_workers", 2, backend="rtx", kind="active"),
            result("knowledge_index_last_run_timestamp_seconds", 5)]
    monkeypatch.setattr(observer.subprocess, "check_output", lambda *a, **kw: json.dumps(
        {"status": "success", "data": {"result": rows}}).encode())
    snapshot = observer.collect(1000, Path("test"))["workloads"]
    assert snapshot[CRICKET]["observations"]["mac_active_workers"] == 0
    assert snapshot[CRICKET]["observations"]["mac_desired_workers"] == 4
    assert snapshot[CRICKET]["observations"]["queued_jobs_all_backends"] is None
    assert not snapshot[KI]["fresh"] and not snapshot[PET]["fresh"]
