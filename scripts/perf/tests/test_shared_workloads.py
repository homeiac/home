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

FACE = "library-face-observations"


def window():
    def row(count, unit):
        return dict(demand=True, verified=count, unit=unit, cohort="matched-replay",
                    completed_items=10, p95_s=2, terminal_error_rate=0, quality_ok=True, slo_ok=True, baseline_preserved=True)
    baseline = dict(start_ns=WINDOW, end_ns=2*WINDOW, warmed=True, max_sample_gap_s=15, environment="fixed-models-and-worker-floors",
                    callers={SLOTS: [CRICKET, KI], METAL: [CRICKET, KI]},
                    workloads={CRICKET: row(10, "reviewed source minutes"), KI: row(35, "verified captions"),
                               FACE: row(25, "verified faces"),
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
    assert decision["affected"] == sorted([KI, CRICKET, PET, FACE])
    assert decision["verified_change_percent"] == {CRICKET: 20.0, KI: 0.0, FACE: 0.0}


def test_cricket_requires_a_measurement_for_the_photo_peer():
    sample = window()
    del sample["comparison"]["trial"]["workloads"][FACE]
    report = shared_context(sample, 3*WINDOW)
    assert report["decision"] == "hold"
    assert any(FACE in reason for reason in report["reasons"])


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
    rows = [result("knowledge_index_photo_stage_updated_timestamp_seconds", 990, stage=FACE),
            result("knowledge_index_photo_stage_updated_timestamp_seconds", 50, stage="life-stage"),
            result("knowledge_index_photo_stage_backend_completed", 14, stage=FACE, backend="mac-metal"),
            result("knowledge_index_photo_stage_backend_completed", 300, stage="life-stage", backend="mac-metal"),
            result("knowledge_index_photo_stage_items", 0, stage=FACE, state="pending"),
            result("cricket_heartbeat_timestamp_seconds", 999),
            result("cricket_workers", 4, backend="mac", kind="desired"),
            result("cricket_workers", 0, backend="mac", kind="active"),
            result("cricket_workers", 2, backend="rtx", kind="active"),
            result("knowledge_index_last_run_timestamp_seconds", 5)]
    monkeypatch.setattr(observer.subprocess, "check_output", lambda *a, **kw: json.dumps(
        {"status": "success", "data": {"result": rows}}).encode())
    snapshot = observer.collect(1000, Path("test"))["workloads"]
    face = snapshot[FACE]
    assert face["fresh"] and face["source_age_s"] == 10
    assert face["observations"]["mac_saved_faces"] == 14
    assert face["observations"]["rtx_saved_faces"] is None
    assert face["observations"]["pending_faces"] == 0
    assert snapshot[CRICKET]["observations"]["mac_active_workers"] == 0
    assert snapshot[CRICKET]["observations"]["mac_desired_workers"] == 4
    assert snapshot[CRICKET]["observations"]["queued_jobs_all_backends"] is None
    assert not snapshot[KI]["fresh"] and not snapshot[PET]["fresh"]


def test_observer_keeps_face_work_separate_from_caption_progress(monkeypatch):
    spec = importlib.util.spec_from_file_location("observe_extended", PERF / "observe-shared-workloads.py")
    observer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(observer)
    def point(name, value, **labels):
        return dict(metric=dict(__name__=name, **labels), value=[1000, str(value)])
    rows = [
        point("knowledge_index_photo_stage_updated_timestamp_seconds", 999, stage="library-face-observations"),
        point("knowledge_index_photo_stage_items", 27, stage="library-face-observations", state="pending"),
        point("knowledge_index_photo_stage_items", 500, stage="library-ocr-tags", state="pending"),
        point("knowledge_index_photo_stage_backend_completed", 12, stage="library-face-observations", backend="mac-metal"),
        point("photo_frigate_last_poll_timestamp_seconds", 999),
        point("photo_frigate_service_up", 1, id="frigate_service"),
        point("photo_frigate_processing_milliseconds", 7, kind="detector"),
        point("immich_observer_last_success_timestamp_seconds", 999, source="queues"),
        point("immich_queue_jobs", 3, queue="face_detection", state="active"),
        point("immich_queue_jobs", 9, queue="smart_search", state="active"),
    ]
    monkeypatch.setattr(observer.subprocess, "check_output", lambda *a, **kw: json.dumps(
        {"status": "success", "data": {"result": rows}}).encode())
    snapshot = observer.collect(1000, Path("fixture"))["workloads"]
    faces = snapshot[FACE]["observations"]
    assert faces["pending_faces"] == 27 and faces["mac_saved_faces"] == 12
    assert faces["running_faces"] is None
    assert snapshot["frigate"]["observations"]["detector_rolling_mean_ms"] == 7
    assert "p95_s" not in snapshot["frigate"]["observations"]
    assert snapshot["immich"]["observations"]["face_detection_active"] == 3
    assert snapshot["immich"]["observations"]["facial_recognition_active"] is None


def test_observer_never_collapses_distinct_equal_enricher_streams(monkeypatch):
    spec = importlib.util.spec_from_file_location("observe_streams", PERF / "observe-shared-workloads.py")
    observer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(observer)
    rows = [dict(metric=dict(__name__="media_pipeline_heartbeat_timestamp_seconds", enricher=name), value=[1000, "999"])
            for name in ("first", "second")]
    monkeypatch.setattr(observer.subprocess, "check_output", lambda *a, **kw: json.dumps(
        {"status": "success", "data": {"result": rows}}).encode())
    row = observer.collect(1000, Path("fixture"))["workloads"]["knowledge-index/media-summary"]
    assert not row["fresh"] and row["observations"] == {}
