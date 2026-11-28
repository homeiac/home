"""Exercise the shared-workload agent's commands on synthetic, closed captures."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PERF = Path(__file__).resolve().parents[1]
ROOT = PERF.parents[1]
sys.path.insert(0, str(ROOT / "scripts/knowledge-index"))
from test_media_observations import batch

WORKLOAD = "cricket-indexer"
POOL = "mac-m5/bonsai-slots"
DEVICE = "mac-m5/metal"
WINDOW = 300 * 10**9
NOW = 2_000_000_000_000


def run(d, command, *options, success=True):
    result = subprocess.run([sys.executable, str(PERF / "workload.py"), command,
                             "--session", str(d / "session.json"), *options], text=True, capture_output=True)
    if not success:
        assert result.returncode != 0
        return result.stderr
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def attrs(**values):
    return [{"key": k, "value": {"stringValue": v}} for k, v in values.items()]


def put(d, name, values):
    (d / name).write_text("".join(json.dumps(v) + "\n" for v in values))


@pytest.fixture
def state(tmp_path):
    d = tmp_path
    prepared = run(d, "start", "--workload", WORKLOAD, "--run-id", "fixture", "--stage", "classify",
                   "--resource", POOL, "--output-kind", "media")
    assert prepared["registered_peers"] == ["immich-pet-tagger", "knowledge-index", "library-face-observations"]
    assert set(prepared["resources"]) == {POOL, DEVICE}
    labels = attrs(**{"service.name": WORKLOAD, "workload.run.id": "fixture", "host.name": "mac"})
    span = {"traceId": "ab" * 16, "spanId": "ab" * 8, "startTimeUnixNano": str(NOW - 1000),
            "endTimeUnixNano": str(NOW), "attributes": attrs(**{"workload.stage.id": "classify", "workload.stage": "job"})}
    traces = {"resourceSpans": [{"resource": {"attributes": labels}, "scopeSpans": [{"spans": [span]}]}]}
    old = ROOT / "docs/experiments/waffles/otel-replay/queue.otlp.jsonl"
    logs = json.loads(old.read_text())
    logs["resourceLogs"][0]["resource"]["attributes"] = labels
    for event in logs["resourceLogs"][0]["scopeLogs"][0]["logRecords"]:
        event["timeUnixNano"] = str(NOW)
    put(d, "traces-and-logs.jsonl", [traces, logs])
    point = dict(attributes=attrs(workload=WORKLOAD, backend=POOL, stage_id="classify"), timeUnixNano=str(NOW))
    metrics = [{"name": "workload.verified", "unit": "{item}", "sum": {"isMonotonic": True, "aggregationTemporality": 2,
                "dataPoints": [{**point, "asInt": "12"}]}},
               {"name": "workload.stage.duration", "unit": "s", "histogram": {"aggregationTemporality": 2,
                "dataPoints": [{**point, "count": "1", "bucketCounts": ["1"]}]}}]
    put(d, "metrics.jsonl", [{"resourceMetrics": [{"scopeMetrics": [{"metrics": metrics}]}]}])
    (d / "watermark-ns").write_text(str(NOW))
    return d


def test_registered_trial_with_peers_and_media(state):
    d = state
    receipt = run(d, "diagnose")
    assert receipt["decision"]["action"] == "index_ready_fifo"
    assert run(d, "diagnose", success=False)
    assert run(d, "review")["fleet_review"]["decision"] == "hold"
    peer = "knowledge-index"
    rows = {w: dict(demand=True, unit="items", cohort="matched", verified=10, completed_items=10, p95_s=2, terminal_error_rate=0, quality_ok=True,
                    slo_ok=True, baseline_preserved=True) for w in [WORKLOAD, peer]}
    rows["immich-pet-tagger"] = dict(demand=False, baseline_preserved=True,
                                    activity=dict(state="idle", runnable=0, reservation_workers=0,
                                                  observed_ns=NOW, evidence_ref="fixture/idle"))
    rows["library-face-observations"] = json.loads(json.dumps(rows["immich-pet-tagger"]))
    before = dict(start_ns=NOW-WINDOW, end_ns=NOW, warmed=True, max_sample_gap_s=15, environment="fixed",
                  callers={POOL: [WORKLOAD, peer], DEVICE: [WORKLOAD, peer]}, workloads=rows)
    during = json.loads(json.dumps(before))
    during.update(start_ns=NOW, end_ns=NOW+WINDOW)
    for idle in ("immich-pet-tagger", "library-face-observations"):
        during["workloads"][idle]["activity"]["observed_ns"] = NOW+WINDOW
    during["workloads"][WORKLOAD]["verified"] = 12
    cmp = dict(subject=WORKLOAD, resources=[POOL], action="index_ready_fifo", min_gain=.05,
               max_peer_loss=0, baseline=before, trial=during)
    (d / "watermark-ns").write_text(str(NOW+WINDOW))
    put(d, "comparison.json", [cmp])
    schema = os.environ.get("ASAM_OPENLABEL_1_0_SCHEMA")
    if not schema:
        pytest.skip("set ASAM_OPENLABEL_1_0_SCHEMA to exercise official scene validation")
    refs, row = batch()
    put(d, "observations.jsonl", [next(r for r in refs if r["workload"] == WORKLOAD)])
    put(d, "scene-readback.jsonl", [row])
    decision = run(d, "review")
    assert decision["registered_prediction"] == receipt["receipt_sha256"]
    assert decision["fleet_review"]["decision"] == "eligible"
    assert decision["media_readback"]["distinct_scene_revisions_referenced"] == 1
    during["workloads"][peer]["verified"] = 6
    put(d, "comparison.json", [cmp])
    assert run(d, "review")["fleet_review"]["decision"] == "rollback"
    cmp["action"] = "different-intervention"
    put(d, "comparison.json", [cmp])
    assert "does not match" in run(d, "review", success=False)


@pytest.mark.parametrize("file,old,new", [
    ("traces-and-logs.jsonl", "abababababababababababababababab", "0"*32),
    ("traces-and-logs.jsonl", "classify", "unregistered"),
    ("metrics.jsonl", '"stage_id"', '"traceId"'),
    ("metrics.jsonl", '"asInt": "12"', '"asInt": "-1"'),
    ("metrics.jsonl", '"bucketCounts": ["1"]', '"bucketCounts": ["7"]'),
    ("metrics.jsonl", '"{item}"', '"seconds"')])
def test_malformed_instrumentation(state, file, old, new):
    path = state / file
    path.write_text(path.read_text().replace(old,new))
    assert run(state, "review", success=False)
