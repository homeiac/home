"""Exercise outbox recovery and edit fencing against independent PostgreSQL sessions."""

# Imported pytest fixtures are intentionally shadowed by injected parameters.
# ruff: noqa: F811

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

import psycopg
import pytest

from cricket.ledger import Conflict, Ledger, encoded
from cricket.prepare import save_private
from cricket.publication import Publisher
from cricket.telemetry import RunTelemetry
from cricket.test_openlabel import inputs, schema, shared  # noqa: F401
from cricket.test_publication_readback import local_pg  # noqa: F401
from cricket.test_telemetry import (
    run,  # noqa: F401
    spans,
)


@pytest.fixture
def prepared(
    tmp_path: Path, local_pg: object, shared: object, schema: Path, inputs: tuple
) -> tuple:
    asset, registry, events = inputs
    album = str(UUID(int=4))
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    ledger.add_album(asset["owner"], album)
    ledger.add_asset(
        asset["owner"], album, asset["id"], "video", 30, asset["fingerprint"]
    )
    with ledger.connect(True) as db:
        db.execute(
            "INSERT INTO jobs(owner,asset,version,stage,state,checkpoint) VALUES(?,?,?,'analyze','complete',?)",
            (
                asset["owner"],
                asset["id"],
                "v1",
                encoded(
                    {"run": "analysis-fixture", "fingerprint": asset["fingerprint"]}
                ),
            ),
        )
    evidence = tmp_path / "evidence"
    save_private(evidence / "faces" / (asset["id"] + ".json"), registry)
    publisher = Publisher(
        ledger,
        evidence,
        shared,
        schema,
        lambda: psycopg.connect(local_pg.info.dsn, autocommit=True),
    )
    args = (asset["owner"], album, asset["id"], "v1", "fixture", "mac-m5/bonsai-slots")
    return publisher, args, events[0]["data"]


def test_receipt_retry_and_other_run_do_not_inflate_production(
    prepared: tuple, local_pg: object, tmp_path: Path
) -> None:
    publisher, args, _ = prepared
    identity = publisher.enqueue(*args)
    assert publisher.enqueue(*args) == identity
    receipt = publisher.deliver(identity)
    assert publisher.deliver(identity) == receipt
    # New run may reference existing production output, without earning another completion.
    later = publisher.enqueue(*args[:4], "later", args[5])
    publisher.deliver(later)
    assert (
        local_pg.execute("SELECT count(*) FROM openlabel_album_scene").fetchone()[0]
        == 1
    )
    report = publisher.export("later", tmp_path / "later")
    assert report["unique_sources"] == 1 and report["new_production_completions"] == 0
    assert (
        publisher.export("fixture", tmp_path / "first")["new_production_completions"]
        == 1
    )
    assert list(tmp_path.glob("ledger.sqlite3.before-publication-*"))
    with publisher.ledger.connect() as db:
        assert (
            db.execute("SELECT count(*) FROM cricket_verified_source").fetchone()[0]
            == 1
        )
    assert all(p.stat().st_mode & 0o077 == 0 for p in (tmp_path / "first").iterdir())


def test_crash_after_pg_commit_recovers_without_new_revision(
    prepared: tuple, local_pg: object
) -> None:
    publisher, args, _ = prepared
    identity = publisher.enqueue(*args)
    connect = publisher.connect
    calls = 0

    def fail_readback() -> object:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ConnectionError("private connection text")
        return connect()

    publisher.connect = fail_readback
    with pytest.raises(ConnectionError):
        publisher.deliver(identity)
    assert (
        local_pg.execute("SELECT count(*) FROM openlabel_album_scene").fetchone()[0]
        == 1
    )
    with publisher.ledger.connect() as db:
        row = dict(db.execute("SELECT * FROM cricket_publication").fetchone())
        assert row["state"] == "pending" and row["error"] == "ConnectionError"
        assert (
            db.execute("SELECT count(*) FROM cricket_verified_source").fetchone()[0]
            == 0
        )
    publisher = Publisher(
        publisher.ledger,
        publisher.evidence,
        publisher.shared,
        publisher.schema,
        connect,
    )
    assert publisher.deliver(identity)["readback"]["revision"] == 1
    assert (
        local_pg.execute("SELECT count(*) FROM openlabel_album_scene").fetchone()[0]
        == 1
    )


def test_correction_fences_pending_intent_and_new_revision_counts_once(
    prepared: tuple, local_pg: object, tmp_path: Path
) -> None:
    publisher, args, event = prepared
    ledger = publisher.ledger
    eid = ledger.create_event(*args[:3], event)
    pending = publisher.enqueue(*args)
    current = ledger.get(args[0], eid)
    ledger.revise(args[0], eid, current["revision"], patch={"outcome": "four"})
    with pytest.raises(Conflict, match="changed"):
        publisher.deliver(pending)
    assert (
        local_pg.execute("SELECT to_regclass('openlabel_album_scene')").fetchone()[0]
        is None
    )
    first = publisher.deliver(publisher.enqueue(*args))
    current = ledger.get(args[0], eid)
    ledger.revise(args[0], eid, current["revision"], action="dismiss")
    second = publisher.deliver(publisher.enqueue(*args))
    assert first["readback"]["revision"] == 1 and second["readback"]["revision"] == 2
    assert not second["readback"]["scene"]["openlabel"]["actions"]
    report = publisher.export("fixture", tmp_path / "current")
    assert report["distinct_scene_revisions_referenced"] == 1
    assert report["new_production_completions"] == 1


@pytest.mark.parametrize("change", ["source", "analysis", "faces"])
def test_changed_input_cannot_earn_receipt(prepared: tuple, change: str) -> None:
    publisher, args, _ = prepared
    identity = publisher.enqueue(*args)
    if change == "faces":
        path = publisher.evidence / "faces" / (args[2] + ".json")
        value = json.loads(path.read_text())
        value["frames"][0]["faces"][0]["person_id"] = args[0]
        save_private(path, value)
    else:
        with publisher.ledger.connect(True) as db:
            if change == "source":
                db.execute("UPDATE assets SET fingerprint='changed'")
            else:
                db.execute("UPDATE jobs SET state='queued'")
    with pytest.raises(Conflict):
        publisher.deliver(identity)
    with publisher.ledger.connect() as db:
        assert (
            db.execute("SELECT count(*) FROM cricket_verified_source").fetchone()[0]
            == 0
        )


def test_bounded_retries_and_checker_failure_never_count(prepared: tuple) -> None:
    publisher, args, _ = prepared
    identity = publisher.enqueue(*args)
    with patch.object(
        publisher, "connect", side_effect=ConnectionError("private")
    ) as connect:
        for _ in range(3):
            with pytest.raises(ConnectionError):
                publisher.deliver(identity)
        with pytest.raises(Conflict, match="bounded retries"):
            publisher.deliver(identity)
    assert connect.call_count == 3
    with publisher.ledger.connect() as db:
        assert (
            db.execute("SELECT state FROM cricket_publication").fetchone()[0] == "error"
        )
        assert (
            db.execute("SELECT count(*) FROM cricket_verified_source").fetchone()[0]
            == 0
        )


def test_writer_trace_handoff_and_common_media_cli(
    prepared: tuple, run: object, tmp_path: Path
) -> None:
    publisher, args, _ = prepared
    with run.stage("ingest", args[5]):
        parent = run.headers()
    with publisher.ledger.connect(True) as db:
        saved = json.loads(db.execute("SELECT checkpoint FROM jobs").fetchone()[0])
        saved["trace_context"] = parent
        db.execute("UPDATE jobs SET checkpoint=?", (encoded(saved),))
    publisher.telemetry = run
    identity = publisher.enqueue(*args)
    publisher.deliver(identity)
    bundle = tmp_path / "bundle"
    publisher.export("fixture", bundle)
    root = Path(__file__).resolve().parents[3]
    response = subprocess.run(
        [
            sys.executable,
            str(root / "scripts/perf/workload.py"),
            "verify-media",
            "--session",
            str(run.session_path),
            "--references",
            str(bundle / "media-observations.jsonl"),
            "--readback",
            str(bundle / "scene-readback.jsonl"),
            "--schema",
            str(publisher.schema),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(response.stdout)["distinct_scene_revisions_referenced"] == 1
    capture = tmp_path / "capture"
    assert run.close_window(capture)["verified_items"] == 0
    recorded = spans(capture)
    assert {s["name"] for s in recorded} == {
        "cricket.ingest",
        "cricket.publish",
        "cricket.verify",
    }
    assert len({s["traceId"] for s in recorded}) == 1
    assert all(
        s["parentSpanId"] == parent["traceparent"].split("-")[2]
        for s in recorded
        if s["name"] != "cricket.ingest"
    )
    cutoff = int((capture / "watermark-ns").read_text())
    for _ in range(2):
        assert run.sync_verified(publisher.ledger.path, publisher.schema) == 1
    # A receipt first observed after a closed cutoff cannot rewrite that window.
    assert run.close_window(tmp_path / "past", cutoff)["verified_items"] == 0
    out = tmp_path / "with-receipt"
    assert run.close_window(out)["verified_items"] == 1
    packet = json.loads((out / "metrics.jsonl").read_text())
    metric = packet["resourceMetrics"][0]["scopeMetrics"][0]["metrics"][0]
    counted = [p for p in metric["sum"]["dataPoints"] if int(p["asInt"])]
    assert len(counted) == 1 and counted[0]["asInt"] == "1"
    assert {a["key"]: a["value"]["stringValue"] for a in counted[0]["attributes"]} == {
        "workload": "cricket-indexer",
        "stage_id": "verify",
        "backend": args[5],
    }
    review = subprocess.run(
        [
            sys.executable,
            str(root / "scripts/perf/workload.py"),
            "review",
            "--session",
            str(out / "session.json"),
            "--references",
            str(bundle / "media-observations.jsonl"),
            "--readback",
            str(bundle / "scene-readback.jsonl"),
            "--schema",
            str(publisher.schema),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    reviewed = json.loads(review.stdout)
    assert reviewed["media_readback"]["distinct_scene_revisions_referenced"] == 1
    assert reviewed["fleet_review"]["decision"] != "eligible"
    restarted = RunTelemetry(run.session_path)
    try:
        restarted.sync_verified(publisher.ledger.path, publisher.schema)
        assert restarted.close_window(tmp_path / "restarted")["verified_items"] == 1
    finally:
        restarted.shutdown()
    with publisher.ledger.connect(True) as db:
        receipt = json.loads(
            db.execute("SELECT receipt FROM cricket_publication").fetchone()[0]
        )
        receipt["host"] = "different-host"
        db.execute("UPDATE cricket_publication SET receipt=?", (encoded(receipt),))
    with pytest.raises(ValueError, match="scope, host or identity"):
        run.sync_verified(publisher.ledger.path, publisher.schema)


def test_failed_independent_validation_never_counts(prepared: tuple) -> None:
    publisher, args, _ = prepared
    identity = publisher.enqueue(*args)
    with (
        patch("cricket.publication.check", side_effect=ValueError("fixture")),
        pytest.raises(ValueError),
    ):
        publisher.deliver(identity)
    with publisher.ledger.connect() as db:
        assert (
            db.execute("SELECT state FROM cricket_publication").fetchone()[0]
            == "conflict"
        )
        assert (
            db.execute("SELECT count(*) FROM cricket_verified_source").fetchone()[0]
            == 0
        )
