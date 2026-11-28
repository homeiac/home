"""Persist real SDK spans and close private, reproducible shared-workload captures.

Verified output comes only from durable independent publication receipts. Analysis
and model success never increment this counter.
"""

import argparse
import base64
import hashlib
import json
import logging
import math
import os
import socket
import sqlite3
import tempfile
import time
from collections import defaultdict
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path

from google.protobuf.json_format import MessageToDict
from opentelemetry import propagate
from opentelemetry.exporter.otlp.proto.common.trace_encoder import encode_spans
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)
from opentelemetry.trace import Status, StatusCode

from .prepare import save_private


def attributes(values: dict) -> list[dict]:
    """Encode the bounded string fields used on metric resources and points."""
    return [{"key": k, "value": {"stringValue": v}} for k, v in sorted(values.items())]


def otlp_ids(value: object) -> None:
    """Protobuf JSON uses base64 bytes; OTLP requires hexadecimal trace/span IDs."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"traceId", "spanId", "parentSpanId"}:
                value[key] = base64.b64decode(item, validate=True).hex()
            else:
                otlp_ids(item)
    elif isinstance(value, list):
        for item in value:
            otlp_ids(item)


class JournalExporter(SpanExporter):
    """Commit finished spans independently of workers and never export prompt text."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.failure_path = path.with_suffix(".failed")
        self.failed = self.failure_path.exists()

    def export(self, spans: list) -> SpanExportResult:
        try:
            with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
                for span in spans:
                    packet = MessageToDict(encode_spans([span]))
                    otlp_ids(packet)
                    db.execute(
                        "INSERT OR IGNORE INTO spans VALUES(?,?,?,?,?,?,?)",
                        (
                            f"{span.context.trace_id:032x}/{span.context.span_id:016x}",
                            span.start_time,
                            span.end_time,
                            time.time_ns(),
                            span.attributes["workload.stage.id"],
                            span.attributes["workload.backend"],
                            json.dumps(packet),
                        ),
                    )
            return SpanExportResult.SUCCESS
        except (OSError, ValueError, KeyError, sqlite3.Error):
            self.failed = True
            # A separate capture process must not mistake a partial journal for
            # complete telemetry after the worker restarts. Fail this session
            # permanently; start a new session after repairing the exporter.
            fd = os.open(self.failure_path, os.O_WRONLY | os.O_CREAT, 0o600)
            os.close(fd)
            return SpanExportResult.FAILURE


class RunTelemetry:
    """One fixed session and actual host; callers pass context across worker threads."""

    def __init__(self, session: Path, *, host: str | None = None) -> None:
        self.session_path = session
        self.session = json.loads(session.read_text())
        if (
            self.session["workload"] != "cricket-indexer"
            or self.session["output_kind"] != "media"
            or not self.session["run_id"]
        ):
            raise ValueError("Expected a cricket media run session")
        self.host = host or socket.gethostname()
        self.path = session.parent / "telemetry.sqlite3"
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT, 0o600)
        os.close(fd)
        self.path.chmod(0o600)
        digest = hashlib.sha256(
            json.dumps(self.session, sort_keys=True).encode()
        ).hexdigest()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS identity (singleton INTEGER PRIMARY KEY CHECK(singleton=1), digest TEXT, host TEXT)"
            )
            db.execute(
                "INSERT OR IGNORE INTO identity VALUES(1,?,?)", (digest, self.host)
            )
            if db.execute("SELECT digest,host FROM identity").fetchone() != (
                digest,
                self.host,
            ):
                raise ValueError("Telemetry session or actual host changed")
            db.execute(
                "CREATE TABLE IF NOT EXISTS spans (id TEXT PRIMARY KEY, start_ns INTEGER, end_ns INTEGER, received_ns INTEGER, stage TEXT, backend TEXT, packet TEXT)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS configuration (singleton INTEGER PRIMARY KEY CHECK(singleton=1), digest TEXT NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS verified (id TEXT PRIMARY KEY, digest TEXT NOT NULL, backend TEXT NOT NULL, verified_ns INTEGER NOT NULL, received_ns INTEGER NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS receipt_source (singleton INTEGER PRIMARY KEY CHECK(singleton=1), digest TEXT NOT NULL)"
            )
        self.exporter = JournalExporter(self.path)
        self.provider = TracerProvider(
            resource=Resource(
                {
                    "service.name": self.session["workload"],
                    "host.name": self.host,
                    "workload.run.id": self.session["run_id"],
                }
            )
        )
        self.provider.add_span_processor(SimpleSpanProcessor(self.exporter))
        self.tracer = self.provider.get_tracer("cricket", "1")

    def bind_configuration(self, config: dict) -> None:
        """Fence restart/hot reload from changing the experiment except desired lane counts."""
        stable = {
            "analysis_version": config.get("analysis_version", "cricket-v1"),
            "allowed_assets": config.get("allowed_assets"),
            "backends": {
                name: {k: v for k, v in backend.items() if k != "workers"}
                for name, backend in config["backends"].items()
            },
        }
        digest = hashlib.sha256(json.dumps(stable, sort_keys=True).encode()).hexdigest()
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            db.execute("INSERT OR IGNORE INTO configuration VALUES(1,?)", (digest,))
            if db.execute("SELECT digest FROM configuration").fetchone()[0] != digest:
                raise ValueError(
                    "Fixed configuration changed; start a new telemetry session"
                )

    @contextmanager
    def stage(
        self,
        stage: str,
        backend: str,
        *,
        parent: dict | None = None,
        job: dict | None = None,
        whole_job: bool = False,
        inference_window: dict | None = None,
    ) -> Iterator[None]:
        """Time an operation without treating remote request latency as GPU time."""
        if (
            stage not in self.session["stages"]
            or backend not in self.session["resources"]
        ):
            raise ValueError("Undeclared telemetry stage or backend")
        if parent and parent.get("x-workload-run-id") != self.session["run_id"]:
            raise ValueError("Queue context belongs to another run")
        fields = {"workload.stage.id": stage, "workload.backend": backend}
        if whole_job:
            fields["workload.stage"] = "job"
        if job:
            for name in ("asset", "fingerprint", "version", "attempts", "execution_id"):
                if name in job:
                    fields["cricket." + name] = job[name]
        if inference_window is not None:
            expected = {
                "index",
                "count",
                "start_s",
                "end_s",
                "analysis_digest",
                "preparation_digest",
            }
            if (
                stage != "classify"
                or set(inference_window) != expected
                or type(inference_window["index"]) is not int
                or type(inference_window["count"]) is not int
                or not 0 <= inference_window["index"] < inference_window["count"]
                or any(
                    type(inference_window[k]) not in (int, float)
                    or not math.isfinite(inference_window[k])
                    or inference_window[k] < 0
                    for k in ("start_s", "end_s")
                )
                or inference_window["end_s"] < inference_window["start_s"]
                or any(
                    not isinstance(inference_window[k], str) or not inference_window[k]
                    for k in ("analysis_digest", "preparation_digest")
                )
                or not job
                or not job.get("execution_id")
            ):
                raise ValueError("Invalid per-window inference provenance")
            fields.update(
                {"cricket.window." + k: v for k, v in inference_window.items()}
            )
        context = propagate.extract(parent) if parent else None
        with self.tracer.start_as_current_span(
            "cricket." + stage,
            context=context,
            attributes=fields,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            try:
                yield
            except Exception as error:
                span.set_status(Status(StatusCode.ERROR, type(error).__name__))
                raise

    def headers(self) -> dict[str, str]:
        """Pass caller/run identity and W3C trace context to the shared model server."""
        headers = {
            "x-workload-name": self.session["workload"],
            "x-workload-run-id": self.session["run_id"],
        }
        propagate.inject(headers)
        return {
            k: v
            for k, v in headers.items()
            if k
            in {"traceparent", "tracestate", "x-workload-name", "x-workload-run-id"}
        }

    def sync_verified(self, ledger: Path, schema: Path) -> int:
        """Import immutable source receipts once, retaining their first observation time."""
        from check_media_observations import check

        from .ledger import Ledger
        from .publication import digest

        definition = json.loads(schema.read_text())
        source = Ledger(ledger, read_only=True)
        identity = digest([str(source.path), definition])
        with source.connect() as db:
            rows = db.execute(
                "SELECT v.*,p.receipt,p.snapshot,p.owner,p.asset,p.version,p.state,p.digest,p.album,p.revision "
                "FROM cricket_verified_source v JOIN cricket_publication p ON p.id=v.publication WHERE v.run_id=?",
                (self.session["run_id"],),
            ).fetchall()
        checked = []
        for row in rows:
            receipt = json.loads(row["receipt"])
            ref, readback = receipt["reference"], receipt["readback"]
            state = json.loads(row["snapshot"])
            expected = digest(
                [
                    row["owner"],
                    row["asset"],
                    state["source"]["fingerprint"],
                    row["version"],
                    state["analysis_digest"],
                ]
            )
            if (
                row["state"] != "verified"
                or receipt.get("host") != self.host
                or ref["run_id"] != self.session["run_id"]
                or ref["workload"] != self.session["workload"]
                or ref["asset"] != row["asset"]
                or ref["album"] != row["album"]
                or ref["digest"] != row["digest"]
                or ref["revision"] != row["revision"]
                or row["completion_key"] != expected
                or receipt["verified_ns"] != row["verified_ns"]
                or row["verified_ns"] > time.time_ns()
                or row["backend"] not in self.session["resources"]
            ):
                raise ValueError("Publication receipt scope, host or identity mismatch")
            check([ref], [readback], definition)
            checked.append(
                (
                    row["completion_key"],
                    digest(receipt),
                    row["backend"],
                    row["verified_ns"],
                )
            )
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            db.execute("INSERT OR IGNORE INTO receipt_source VALUES(1,?)", (identity,))
            if (
                db.execute("SELECT digest FROM receipt_source").fetchone()[0]
                != identity
            ):
                raise ValueError("Publication receipt source changed")
            for entry in checked:
                prior = db.execute(
                    "SELECT digest,backend,verified_ns FROM verified WHERE id=?",
                    (entry[0],),
                ).fetchone()
                if prior is not None and prior != entry[1:]:
                    raise ValueError("Previously imported receipt changed")
                db.execute(
                    "INSERT OR IGNORE INTO verified VALUES(?,?,?,?,?)",
                    (*entry, time.time_ns()),
                )
        return len(checked)

    def close_window(self, output: Path, cutoff_ns: int | None = None) -> dict:
        """Export an immutable capture, including only evidence received by its cutoff."""
        self.provider.force_flush()
        cutoff_ns = cutoff_ns or time.time_ns()
        if (
            self.exporter.failed
            or self.exporter.failure_path.exists()
            or cutoff_ns > time.time_ns()
            or cutoff_ns <= 0
        ):
            raise ValueError("Telemetry failed or cutoff is invalid")
        with closing(sqlite3.connect(self.path)) as db:
            rows = db.execute(
                "SELECT start_ns,end_ns,stage,backend,packet FROM spans WHERE end_ns<=? AND received_ns<=? ORDER BY end_ns,id",
                (cutoff_ns, cutoff_ns),
            ).fetchall()
            verified = dict(
                db.execute(
                    "SELECT backend,count(*) FROM verified WHERE verified_ns<=? AND received_ns<=? GROUP BY backend",
                    (cutoff_ns, cutoff_ns),
                ).fetchall()
            )
        if not rows:
            raise ValueError("No completed spans at cutoff")
        if output.exists():
            raise FileExistsError("Closed capture already exists")
        durations = defaultdict(list)
        for start, end, stage, backend, _ in rows:
            durations[stage, backend].append((end - start) / 1e9)
        if any(("verify", backend) not in durations for backend in verified):
            raise ValueError("Verified receipt has no matching verification spans")
        histograms, counters = [], []
        for (stage, backend), values in sorted(durations.items()):
            point = {
                "attributes": attributes(
                    {
                        "workload": self.session["workload"],
                        "stage_id": stage,
                        "backend": backend,
                    }
                ),
                "startTimeUnixNano": str(min(row[0] for row in rows)),
                "timeUnixNano": str(cutoff_ns),
            }
            histograms.append(
                {
                    **point,
                    "count": str(len(values)),
                    "sum": sum(values),
                    "explicitBounds": [],
                    "bucketCounts": [str(len(values))],
                }
            )
            count = verified.get(backend, 0) if stage == "verify" else 0
            counters.append({**point, "asInt": str(count)})
        metrics = {
            "resourceMetrics": [
                {
                    "resource": {
                        "attributes": attributes(
                            {
                                "service.name": self.session["workload"],
                                "host.name": self.host,
                            }
                        )
                    },
                    "scopeMetrics": [
                        {
                            "scope": {"name": "cricket"},
                            "metrics": [
                                {
                                    "name": "workload.verified",
                                    "unit": "{item}",
                                    "sum": {
                                        "isMonotonic": True,
                                        "aggregationTemporality": 2,
                                        "dataPoints": counters,
                                    },
                                },
                                {
                                    "name": "workload.stage.duration",
                                    "unit": "s",
                                    "histogram": {
                                        "aggregationTemporality": 2,
                                        "dataPoints": histograms,
                                    },
                                },
                            ],
                        }
                    ],
                }
            ]
        }
        with tempfile.TemporaryDirectory(
            dir=output.parent, prefix=".cricket-capture-"
        ) as folder:
            staging = Path(folder)
            save_private(staging / "session.json", self.session)
            for name, value in (
                ("traces-and-logs.jsonl", "".join(row[4] + "\n" for row in rows)),
                ("metrics.jsonl", json.dumps(metrics) + "\n"),
                ("watermark-ns", str(cutoff_ns) + "\n"),
            ):
                with open(
                    staging / name, "x", opener=lambda p, f: os.open(p, f, 0o600)
                ) as stream:
                    stream.write(value)
            if output.exists():
                raise FileExistsError("Closed capture already exists")
            staging.rename(output)
        return {
            "spans": len(rows),
            "cutoff_ns": cutoff_ns,
            "verified_items": sum(verified.values()),
        }

    def shutdown(self) -> None:
        """Finish export without changing any workload allocation."""
        self.provider.shutdown()


def main() -> None:
    """Close a capture from an existing run journal without dispatching new work."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--at-ns", type=int)
    parser.add_argument("--publication-ledger", type=Path)
    parser.add_argument("--schema", type=Path)
    args = parser.parse_args()
    if bool(args.publication_ledger) != bool(args.schema):
        parser.error("--publication-ledger and --schema must be supplied together")
    telemetry = RunTelemetry(args.session)
    try:
        if args.publication_ledger:
            telemetry.sync_verified(args.publication_ledger, args.schema)
        report = telemetry.close_window(args.output, args.at_ns)
    finally:
        telemetry.shutdown()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger(__name__).info("%s", json.dumps(report))


if __name__ == "__main__":
    main()
