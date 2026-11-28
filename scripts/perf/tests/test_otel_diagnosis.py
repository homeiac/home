"""Regression tests for cutoff isolation, actual OTLP encodings, and diagnostic specificity."""
import base64
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

PERF = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PERF))
from otel_diagnosis import GPU, QUEUE, decide, digest, predict, read_window

ROOT = PERF.parents[1]
DATA = ROOT / "docs/experiments/waffles/otel-replay"


def capture(case):
    return json.loads((DATA / f"{case}.otlp.jsonl").read_text())


def frozen(case):
    return json.loads((DATA / f"{case}.prediction.json").read_text())


def records(packet):
    return packet["resourceLogs"][0]["scopeLogs"][0]["logRecords"]


def write(tmp, packets):
    path = tmp / "input.jsonl"
    path.write_text("\n".join(json.dumps(p) for p in packets))
    return path


@pytest.mark.parametrize("case,action", [("queue", QUEUE), ("gpu", GPU)])
def test_receipt_and_reordering(case, action, tmp_path):
    expected = frozen(case)
    packet = capture(case)
    records(packet).reverse()
    path = write(tmp_path, [packet, packet])
    result = predict(path, int(expected["as_of_unix_ns"]), expected["window_s"])
    assert result["decision"]["action"] == action
    assert json.loads(json.dumps(result)) == expected


def test_no_future_late_or_stale_evidence(tmp_path):
    packet = capture("queue")
    events = records(packet)
    cutoff = int(frozen("queue")["as_of_unix_ns"])
    for timestamp, observed in [(cutoff + 1, 0), (cutoff - 1, cutoff + 1), (cutoff - 601 * 10**9, 0)]:
        events[1].update(timeUnixNano=str(timestamp), observedTimeUnixNano=str(observed))
        events[1]["attributes"] = []  # excluded before reading even malformed facts
        result = predict(write(tmp_path, [packet]), cutoff, 600)
        assert result["decision"]["state"] == "need_evidence"
        assert "successful ready-claim" in result["decision"]["next_probe"]


def test_mixed_hosts_fail_closed(tmp_path):
    pkt = capture("gpu")
    other = deepcopy(pkt)
    labels = other["resourceLogs"][0]["resource"]["attributes"]
    next(x for x in labels if x["key"] == "host.name")["value"] = {"stringValue": "control"}
    with pytest.raises(ValueError, match="single service"):
        read_window(write(tmp_path, [pkt, other]), int(frozen("gpu")["as_of_unix_ns"]), 600)


@pytest.mark.parametrize("event,field,value", [
    ("db.claim.plan", "returned", 0), ("db.claim.plan", "latency_ms", 1),
    ("db.claim.plan", "sort_input_rows", 2), ("db.claim.plan", "order_keys", ""),
    ("worker.cycle", "samples", 1),
    ("worker.profile", "accelerator_stage_fraction", 0.2),
    ("device.sample", "worker_present", True), ("device.sample", "utilization_pct", 2)])
def test_negative_controls(event, field, value):
    case = "gpu" if event in ("worker.profile", "device.sample") else "queue"
    _, facts = read_window(DATA / f"{case}.otlp.jsonl", int(frozen(case)["as_of_unix_ns"]), 600)
    for _, _, name, d in facts:
        if name == event:
            d[field] = value
    assert decide(facts)["state"] == "need_evidence"


def test_probe_then_trial_on_stream(tmp_path):
    packet = capture("queue")
    records(packet).pop()  # only initial cycle sampling is available
    paths = [write(tmp_path, [packet]), DATA / "queue.otlp.jsonl"]
    checkpoints = [dict(capture=str(path), as_of_unix_ns=frozen("queue")["as_of_unix_ns"]) for path in paths]
    out = subprocess.check_output([sys.executable, str(PERF / "otel-diagnosis-loop.py")],
                                  input="\n".join(map(json.dumps, [{}, *checkpoints])), text=True)
    error, probe, prediction = map(json.loads, out.splitlines())
    assert error["state"] == "invalid_checkpoint"
    assert probe["diagnosis"]["decision"]["state"] == "need_evidence"
    assert prediction["diagnosis"] == frozen("queue")
    assert prediction["fleet_review"]["decision"] == "observe_only"


def test_real_sdk_trace_encoding_with_overlapping_stages(tmp_path):
    from google.protobuf.json_format import MessageToDict, ParseDict
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.common.trace_encoder import encode_spans
    from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    packet = capture("gpu")
    # Check that the replayed observation records are actual OTLP protobuf JSON.
    ParseDict(packet, ExportLogsServiceRequest())
    records(packet)[:] = [ev for ev in records(packet) if ev["eventName"] == "device.sample"]
    resource = Resource.create({"service.name": "immich-pet-tagger", "host.name": "mac",
                                "workload.run.id": "device-window"})
    provider = TracerProvider(resource=resource)
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("diagnosis-regression")
    cutoff = int(frozen("gpu")["as_of_unix_ns"])
    for i in range(10):
        start = cutoff - (i + 1) * 1000
        job = tracer.start_span("unit", start_time=start, attributes={"workload.stage": "job"})
        for lo, hi in [(0, 60), (40, 80)]:
            child = tracer.start_span("unit.stage", context=trace.set_span_in_context(job),
                                      start_time=start + lo, attributes={"workload.stage": "accelerator"})
            child.end(end_time=start + hi)
        job.end(end_time=start + 100)
    # Protobuf JSON's default bytes encoding is base64. OTLP uses hex for IDs.
    request = encode_spans(exporter.get_finished_spans())
    trace_packet = MessageToDict(request)
    for group in trace_packet["resourceSpans"][0]["scopeSpans"]:
        for span in group["spans"]:
            for key in ("traceId", "spanId", "parentSpanId"):
                if key in span:
                    span[key] = base64.b64decode(span[key]).hex()
    result = predict(write(tmp_path, [packet, trace_packet, trace_packet]), cutoff, 600)
    assert result["decision"]["action"] == GPU
    assert result["decision"]["evidence"]["accelerator_stage_fraction_range"] == [0.8, 0.8]
    provider.shutdown()


@pytest.mark.parametrize("case", ["queue", "gpu"])
def test_heldout_score_and_tamper_rejection(case, tmp_path):
    scorer = ROOT / "scripts/immich-pet-tagger/per-worker/score-diagnosis-replay.py"
    cmd = [sys.executable, str(scorer), case]
    result = subprocess.check_output([*cmd, DATA / f"{case}.prediction.json"], text=True)
    assert json.loads(result)["result"]["supported"]
    tampered = frozen(case)
    tampered["decision"]["action"] = "unrelated"
    tampered["receipt_sha256"] = digest({k: v for k, v in tampered.items() if k != "receipt_sha256"})
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(tampered))
    failed = subprocess.run([*cmd, path], capture_output=True, text=True)
    assert failed.returncode and "differs from the registered" in failed.stderr
