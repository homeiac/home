"""Real SDK context crosses claims/threads; captures never count model replies as verified."""

import copy
import io
import json
import subprocess
import sys
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pytest

from cricket.jobs import claim, failed
from cricket.ledger import Ledger
from cricket.models import infer
from cricket.prepare import save_private
from cricket.telemetry import RunTelemetry
from cricket.worker import process

POOL = "mac-m5/bonsai-slots"
ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def run(tmp_path: Path) -> Iterator[RunTelemetry]:
    """Use the real intake command to generate an unmodified run session."""
    session = tmp_path / "session.json"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/perf/workload.py"),
            "start",
            "--session",
            str(session),
            "--workload",
            "cricket-indexer",
            "--run-id",
            "fixture",
            "--output-kind",
            "media",
            "--resource",
            POOL,
            *[
                arg
                for name in (
                    "ingest",
                    "load-evidence",
                    "analyze",
                    "classify",
                    "reconcile",
                    "publish",
                    "verify",
                )
                for arg in ("--stage", name)
            ],
        ],
        check=True,
        capture_output=True,
    )
    telemetry = RunTelemetry(session)
    yield telemetry
    telemetry.shutdown()


def packets(folder: Path) -> list[dict]:
    """Read the closed trace stream as the common CLI does."""
    return [
        json.loads(line)
        for line in (folder / "traces-and-logs.jsonl").read_text().splitlines()
    ]


def spans(folder: Path) -> list[dict]:
    """Flatten spans without changing their SDK identifiers or timing."""
    return [
        span
        for packet in packets(folder)
        for r in packet["resourceSpans"]
        for scope in r["scopeSpans"]
        for span in scope["spans"]
    ]


def test_partial_cache_retry_preserves_distinct_execution_and_window_evidence(
    run: RunTelemetry, tmp_path: Path
) -> None:
    ledger = Ledger(tmp_path / "retry.sqlite3")
    ledger.add_album("o", "a", "person")
    ledger.add_asset("o", "a", "v", "video", 20, "source-v1")
    with ledger.connect(True) as db:
        db.execute(
            "INSERT INTO jobs(owner,asset,version,stage) VALUES('o','v','v1','analyze')"
        )
    evidence = tmp_path / "evidence"
    save_private(
        evidence / "v.json",
        {
            "asset": "v",
            "cache_key": "fixture",
            "windows": [{"start": 0, "end": 10}, {"start": 10, "end": 20}],
        },
    )
    backend = {"model": "fixture", "api": "openai", "resource": POOL}
    album = {"id": "a", "default_batter": "person"}
    with run.stage("ingest", POOL):
        job = claim(ledger, "o", "a", "v1", evidence, trace_context=run.headers())
    with (
        patch(
            "cricket.worker.analyze_one",
            side_effect=[{"proposals": []}, RuntimeError("private error detail")],
        ),
        pytest.raises(RuntimeError),
    ):
        process(ledger, album, job, backend, evidence, tmp_path / "state", None, run)
    failed(ledger, job, "retry")
    with run.stage("ingest", POOL):
        retry = claim(
            ledger,
            "o",
            "a",
            "v1",
            evidence,
            now=time.time() + 120,
            trace_context=run.headers(),
        )
    with patch("cricket.worker.analyze_one", return_value={"proposals": []}) as model:
        process(ledger, album, retry, backend, evidence, tmp_path / "state", None, run)
        assert model.call_count == 1
    capture = tmp_path / "retry-capture"
    assert run.close_window(capture)["verified_items"] == 0
    recorded = spans(capture)
    parents = [s for s in recorded if s["name"] == "cricket.analyze"]
    assert len(parents) == 2

    def fields(span: dict) -> dict:
        return {a["key"]: next(iter(a["value"].values())) for a in span["attributes"]}

    assert len({fields(p)["cricket.execution_id"] for p in parents}) == 2
    successful = next(
        p
        for p in parents
        if p.get("status", {}).get("code") not in (2, "STATUS_CODE_ERROR")
    )
    children = [
        s
        for s in recorded
        if s["name"] == "cricket.classify" and s["parentSpanId"] == successful["spanId"]
    ]
    assert len(children) == 1
    assert int(fields(children[0])["cricket.window.index"]) == 1
    assert int(fields(children[0])["cricket.window.count"]) == 2
    assert (
        fields(children[0])["cricket.execution_id"]
        == fields(successful)["cricket.execution_id"]
    )
    assert "private error detail" not in (capture / "traces-and-logs.jsonl").read_text()


@pytest.mark.parametrize(
    "change",
    [
        {"index": True},
        {"count": 0},
        {"end_s": float("nan")},
        {"start_s": 2},
        {"raw_prompt": "must not enter telemetry"},
    ],
)
def test_invalid_window_provenance_is_rejected(run: RunTelemetry, change: dict) -> None:
    window = {
        "index": 0,
        "count": 1,
        "start_s": 0,
        "end_s": 1,
        "analysis_digest": "a" * 64,
        "preparation_digest": "b" * 64,
        **change,
    }
    with (
        pytest.raises(ValueError, match="per-window"),
        run.stage(
            "classify", POOL, job={"execution_id": "fixture"}, inference_window=window
        ),
    ):
        pass


def test_claim_thread_model_context_and_common_review(
    run: RunTelemetry, tmp_path: Path
) -> None:
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    ledger.add_album("o", "a", "person")
    ledger.add_asset("o", "a", "v", "video", 20, "source-v1")
    with ledger.connect(True) as db:
        db.execute(
            "INSERT INTO jobs(owner,asset,version,stage) VALUES('o','v','v1','analyze')"
        )
    evidence = tmp_path / "evidence"
    save_private(
        evidence / "v.json",
        {"asset": "v", "cache_key": "fixture", "windows": [{"start": 0, "end": 20}]},
    )
    with run.stage("ingest", POOL):
        job = claim(ledger, "o", "a", "v1", evidence, trace_context=run.headers())
    with ledger.connect() as db:
        checkpoint = json.loads(db.execute("SELECT checkpoint FROM jobs").fetchone()[0])
    assert checkpoint["trace_context"] == job["trace_context"]
    backend = {"model": "fixture", "api": "openai", "resource": POOL}
    with (
        patch("cricket.worker.analyze_one", return_value={"proposals": []}) as model,
        ThreadPoolExecutor(1) as pool,
    ):
        pool.submit(
            process,
            ledger,
            {"id": "a", "default_batter": "person"},
            job,
            backend,
            evidence,
            tmp_path / "answers",
            None,
            run,
        ).result()
    headers = model.call_args.kwargs["caller_headers"]
    assert headers["x-workload-name"] == "cricket-indexer"
    assert headers["x-workload-run-id"] == "fixture"
    assert (
        headers["traceparent"].split("-")[1]
        == job["trace_context"]["traceparent"].split("-")[1]
    )
    capture = tmp_path / "closed"
    report = run.close_window(capture)
    assert report["verified_items"] == 0
    recorded = spans(capture)
    by_name = {s["name"]: s for s in recorded}
    assert len({s["traceId"] for s in recorded}) == 1
    assert (
        by_name["cricket.analyze"]["parentSpanId"]
        == by_name["cricket.ingest"]["spanId"]
    )
    assert (
        by_name["cricket.classify"]["parentSpanId"]
        == by_name["cricket.analyze"]["spanId"]
    )
    assert headers["traceparent"].split("-")[2] == by_name["cricket.classify"]["spanId"]
    fields = {
        a["key"]: next(iter(a["value"].values()))
        for a in by_name["cricket.classify"]["attributes"]
    }
    parent_fields = {
        a["key"]: next(iter(a["value"].values()))
        for a in by_name["cricket.analyze"]["attributes"]
    }
    assert fields["cricket.execution_id"] == parent_fields["cricket.execution_id"]
    assert len(fields["cricket.execution_id"]) == 32
    assert (
        fields["cricket.asset"] == "v" and fields["cricket.fingerprint"] == "source-v1"
    )
    assert (
        int(fields["cricket.window.index"]) == 0
        and int(fields["cricket.window.count"]) == 1
    )
    assert (
        int(fields["cricket.window.start_s"]) == 0
        and int(fields["cricket.window.end_s"]) == 20
    )
    assert len(fields["cricket.window.analysis_digest"]) == 64
    response = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/perf/workload.py"),
            "review",
            "--session",
            str(capture / "session.json"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    reviewed = json.loads(response.stdout)
    assert reviewed["telemetry"]["traces"]["spans"] == report["spans"]
    assert reviewed["fleet_review"]["decision"] == "hold"
    assert reviewed["media_readback"] is None
    assert all(path.stat().st_mode & 0o077 == 0 for path in capture.iterdir())


def test_restart_retry_cutoff_and_immutable_capture(
    run: RunTelemetry, tmp_path: Path
) -> None:
    with run.stage("ingest", POOL):
        first = run.headers()
    cutoff = time.time_ns()
    with run.stage("ingest", POOL):
        retry = run.headers()
    assert first["traceparent"] != retry["traceparent"]
    reopened = RunTelemetry(run.session_path)
    try:
        out = tmp_path / "past"
        assert reopened.close_window(out, cutoff)["spans"] == 1
        digest = (out / "traces-and-logs.jsonl").read_bytes()
        with pytest.raises(FileExistsError):
            reopened.close_window(out)
        assert (out / "traces-and-logs.jsonl").read_bytes() == digest
        assert reopened.close_window(tmp_path / "all")["spans"] == 2
    finally:
        reopened.shutdown()


def test_errors_do_not_capture_exception_payloads_or_fake_accelerator_time(
    run: RunTelemetry, tmp_path: Path
) -> None:
    with pytest.raises(RuntimeError), run.stage("classify", POOL):
        raise RuntimeError("private response text must not be exported")
    out = tmp_path / "closed"
    run.close_window(out)
    raw = (out / "traces-and-logs.jsonl").read_text()
    assert "private response" not in raw and "accelerator" not in raw
    assert spans(out)[0]["status"]["message"] == "RuntimeError"
    with pytest.raises(ValueError), run.stage("undeclared", POOL):
        pass
    with pytest.raises(ValueError), run.stage("classify", "unknown-device"):
        pass


def test_run_and_fixed_configuration_are_fenced(
    run: RunTelemetry, tmp_path: Path
) -> None:
    config = {
        "backends": {
            "mac": {
                "workers": 4,
                "max_workers": 4,
                "resource": POOL,
                "model": "fixture",
            }
        }
    }
    run.bind_configuration(config)
    less = copy.deepcopy(config)
    less["backends"]["mac"]["workers"] = 2
    run.bind_configuration(less)
    less["backends"]["mac"]["model"] = "different"
    with pytest.raises(ValueError, match="configuration changed"):
        run.bind_configuration(less)
    with (
        pytest.raises(ValueError, match="another run"),
        run.stage("classify", POOL, parent={"x-workload-run-id": "other"}),
    ):
        pass
    changed = json.loads(run.session_path.read_text())
    changed["run_id"] = "changed"
    run.session_path.write_text(json.dumps(changed))
    with pytest.raises(ValueError, match="session or actual host changed"):
        RunTelemetry(run.session_path)


def test_http_transport_forwards_only_caller_context() -> None:
    headers = {
        "traceparent": "00-" + "1" * 32 + "-" + "2" * 16 + "-01",
        "x-workload-name": "cricket-indexer",
        "x-workload-run-id": "fixture",
    }
    with patch(
        "cricket.models.urllib.request.urlopen",
        return_value=io.BytesIO(b'{"choices":[{"message":{"content":"ok"}}]}'),
    ) as request:
        assert (
            infer(
                {"api": "openai", "endpoint": "http://fixture", "model": "fixture"},
                "fixture",
                [],
                caller_headers=headers,
            )
            == "ok"
        )
    actual = {k.lower(): v for k, v in request.call_args.args[0].header_items()}
    assert headers.items() <= actual.items()
    with pytest.raises(ValueError, match="Unexpected caller header"):
        infer(
            {"api": "openai", "endpoint": "http://fixture", "model": "fixture"},
            "fixture",
            [],
            caller_headers={"Authorization": "synthetic"},
        )


def test_export_failure_survives_restart_and_prevents_partial_capture(
    run: RunTelemetry, tmp_path: Path
) -> None:
    with run.stage("ingest", POOL):
        pass
    with (
        patch("cricket.telemetry.sqlite3.connect", side_effect=OSError("disk")),
        run.stage("classify", POOL),
    ):
        pass
    reopened = RunTelemetry(run.session_path)
    try:
        with pytest.raises(ValueError, match="Telemetry failed"):
            reopened.close_window(tmp_path / "partial")
        assert not (tmp_path / "partial").exists()
    finally:
        reopened.shutdown()


@pytest.mark.parametrize("transport", ["ssh", "qga"])
def test_remote_transports_forward_caller_context(transport: str) -> None:
    headers = {"x-workload-run-id": "fixture", "x-workload-name": "cricket-indexer"}
    response = {"choices": [{"message": {"content": "ok"}}]}
    if transport == "qga":
        response = {"exited": True, "exitcode": 0, "out-data": json.dumps(response)}
    with patch("cricket.models.subprocess.run") as request:
        request.return_value.returncode = 0
        request.return_value.stdout = json.dumps(response)
        assert (
            infer(
                {
                    "api": "openai",
                    "endpoint": "http://fixture",
                    "model": "fixture",
                    "transport": transport,
                    "host": "fixture",
                },
                "fixture",
                [],
                caller_headers=headers,
            )
            == "ok"
        )
    if transport == "ssh":
        assert json.loads(request.call_args.kwargs["input"])["headers"] == headers
    else:
        command = request.call_args.args[0][-1]
        assert all(k + ": " + v in command for k, v in headers.items())
