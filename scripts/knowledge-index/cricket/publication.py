"""Recoverable OpenLABEL publication with independent SQL readback and durable receipts.

This opt-in extension adds tables to the operational ledger after an online
backup. Existing proposals, jobs and corrections remain authoritative. Production
verified counts are distinct from the number of referenced scene occurrences.
"""

import argparse
import hashlib
import json
import logging
import time
from collections.abc import Callable
from contextlib import nullcontext
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING
from uuid import uuid4

from check_media_observations import check, pg_digest

from .ledger import Conflict, Ledger, backup, encoded, require_text
from .openlabel import publish, registry_for_scene, scene, shared_module
from .prepare import save_private
from .vocabulary import COMPLETION

if TYPE_CHECKING:
    from .telemetry import RunTelemetry

DDL = (
    """CREATE TABLE IF NOT EXISTS cricket_publication (
    id TEXT PRIMARY KEY, owner TEXT NOT NULL, album TEXT NOT NULL, asset TEXT NOT NULL,
    version TEXT NOT NULL, run_id TEXT NOT NULL, backend TEXT NOT NULL,
    snapshot TEXT NOT NULL, scene TEXT NOT NULL, digest TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
    error TEXT, revision INTEGER, receipt TEXT, verified_ns INTEGER,
    completion_key TEXT NOT NULL, trace_context TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS cricket_verified_source (
    completion_key TEXT PRIMARY KEY, publication TEXT NOT NULL,
    run_id TEXT NOT NULL, backend TEXT NOT NULL, verified_ns INTEGER NOT NULL)""",
)


def digest(value: object) -> str:
    """Hash a stable private snapshot without putting its identifiers in logs."""
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def snapshot(db: object, owner: str, album: str, asset: str, version: str) -> dict:
    """Read effective corrections and completed analysis in one ledger transaction."""
    source = Ledger._asset(db, owner, album, asset)
    job = db.execute(
        "SELECT * FROM jobs WHERE owner=? AND asset=? AND version=? AND stage='analyze'",
        (owner, asset, version),
    ).fetchone()
    if job is None or job["state"] != "complete":
        raise Conflict("Analysis is not complete")
    checkpoint = json.loads(job["checkpoint"])
    if checkpoint.get("fingerprint") != source["fingerprint"] or not checkpoint.get(
        "run"
    ):
        raise Conflict("Completed analysis needs a matching source fingerprint")
    events = [
        Ledger._effective(db, dict(row))
        for row in db.execute(
            "SELECT * FROM events WHERE owner=? AND album=? AND asset=? ORDER BY id",
            (owner, album, asset),
        )
    ]
    return {
        "source": source,
        "events": events,
        "analysis_version": version,
        "analysis_digest": checkpoint["run"],
        "trace_context": checkpoint.get("trace_context"),
    }


class Publisher:
    """Serialize source edits with publication; recover SQL commits by exact digest."""

    def __init__(
        self,
        ledger: Ledger,
        evidence: Path,
        shared: ModuleType,
        schema: Path,
        connect: Callable,
        *,
        telemetry: "RunTelemetry | None" = None,
    ) -> None:
        self.ledger, self.evidence, self.shared = ledger, evidence, shared
        self.schema, self.connect, self.telemetry = schema, connect, telemetry
        self.definition = json.loads(schema.read_text())
        if telemetry and not {"publish", "verify"} <= set(telemetry.session["stages"]):
            raise ValueError("Declare publication and verification stages first")
        with ledger.connect() as db:
            exists = db.execute(
                "SELECT 1 FROM sqlite_master WHERE name='cricket_publication'"
            ).fetchone()
        if not exists:
            backup(
                ledger.path,
                ledger.path.with_name(
                    ledger.path.name + ".before-publication-" + uuid4().hex
                ),
            )
        with ledger.connect(True) as db:
            for statement in DDL:
                db.execute(statement)

    def enqueue(
        self,
        owner: str,
        album: str,
        asset: str,
        version: str,
        run_id: str,
        backend: str,
    ) -> str:
        """Persist an immutable intent; a new correction gets a separate intent."""
        require_text(run_id)
        require_text(backend)
        if self.telemetry and (
            run_id != self.telemetry.session["run_id"]
            or backend not in self.telemetry.session["resources"]
        ):
            raise ValueError("Publication does not belong to the telemetry session")
        with self.ledger.connect(True) as db:
            state = snapshot(db, owner, album, asset, version)
            registry = registry_for_scene(self.evidence, state["source"])
            doc = scene(
                self.shared,
                state["source"],
                registry,
                state["events"],
                completion={
                    "state": "complete",
                    "analysis_version": version,
                    "analysis_digest": state["analysis_digest"],
                },
            )
            self.shared.validate_scenes({asset: doc}, self.schema)
            # Trace parent is causal provenance, not part of the canonical scene.
            parent = state.pop("trace_context")
            if parent and parent.get("x-workload-run-id") != run_id:
                raise Conflict("Analysis context belongs to another run")
            state["registry_digest"] = digest(registry)
            identity = digest([owner, album, asset, version, run_id, backend, state])
            completion_key = digest(
                [
                    owner,
                    asset,
                    state["source"]["fingerprint"],
                    version,
                    state["analysis_digest"],
                ]
            )
            db.execute(
                "INSERT OR IGNORE INTO cricket_publication(id,owner,album,asset,version,run_id,backend,snapshot,scene,digest,completion_key,trace_context) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    identity,
                    owner,
                    album,
                    asset,
                    version,
                    run_id,
                    backend,
                    encoded(state),
                    encoded(doc),
                    pg_digest(doc),
                    completion_key,
                    encoded(parent or {}),
                ),
            )
        return identity

    def _current(self, db: object, row: dict) -> None:
        state = snapshot(db, row["owner"], row["album"], row["asset"], row["version"])
        state.pop("trace_context")
        state["registry_digest"] = digest(
            registry_for_scene(self.evidence, state["source"])
        )
        if encoded(state) != row["snapshot"]:
            raise Conflict(
                "Publication source, analysis, correction or native faces changed"
            )

    def _stage(self, name: str, row: dict) -> object:
        return (
            self.telemetry.stage(
                name, row["backend"], parent=json.loads(row["trace_context"]) or None
            )
            if self.telemetry
            else nullcontext()
        )

    def deliver(self, identity: str) -> dict:
        """Bound retries; only independently verified committed data earns a receipt."""
        # Reserve the attempt before contacting PostgreSQL, so crashes consume it.
        with self.ledger.connect(True) as db:
            found = db.execute(
                "SELECT * FROM cricket_publication WHERE id=?", (identity,)
            ).fetchone()
            if found is None:
                raise KeyError("Publication intent not found")
            row = dict(found)
            if self.telemetry and (
                row["run_id"] != self.telemetry.session["run_id"]
                or row["backend"] not in self.telemetry.session["resources"]
            ):
                raise Conflict(
                    "Publication intent belongs to another telemetry session"
                )
            if row["state"] == "verified":
                self._current(db, row)
                return json.loads(row["receipt"])
            if row["state"] in {"conflict", "error"} or row["attempts"] >= 3:
                raise Conflict(
                    "Publication requires explicit review after bounded retries"
                )
            db.execute(
                "UPDATE cricket_publication SET attempts=attempts+1 WHERE id=?",
                (identity,),
            )
        try:
            # The short ledger write lock prevents a user correction from changing
            # underneath the SQL commit. PostgreSQL operations use bounded timeouts.
            with self.ledger.connect(True) as db:
                row = dict(
                    db.execute(
                        "SELECT * FROM cricket_publication WHERE id=?", (identity,)
                    ).fetchone()
                )
                if row["state"] == "verified":
                    self._current(db, row)
                    return json.loads(row["receipt"])
                self._current(db, row)
                with (
                    self._stage("publish", row),
                    self.connect() as writer,
                    writer.transaction(),
                ):
                    writer.execute("SET LOCAL statement_timeout='10s'")
                    writer.execute("SET LOCAL lock_timeout='5s'")
                    publish(
                        writer,
                        self.shared,
                        row["album"],
                        {row["asset"]: json.loads(row["scene"])},
                        self.schema,
                    )
                with self._stage("verify", row), self.connect() as reader:
                    with reader.transaction():
                        reader.execute("SET TRANSACTION READ ONLY")
                        reader.execute("SET LOCAL statement_timeout='10s'")
                        committed = reader.execute(
                            "SELECT revision,digest,scene FROM openlabel_album_scene WHERE album=%s AND asset=%s ORDER BY revision DESC LIMIT 1",
                            (row["album"], row["asset"]),
                        ).fetchone()
                    if not committed or committed[1] != row["digest"]:
                        raise Conflict(
                            "Committed scene no longer matches publication intent"
                        )
                    readback = {
                        "album": row["album"],
                        "asset": row["asset"],
                        "revision": committed[0],
                        "digest": committed[1],
                        "scene": committed[2],
                    }
                    doc = committed[2]["openlabel"]
                    uid = next(
                        k for k, v in doc["contexts"].items() if v["type"] == COMPLETION
                    )
                    reference = {
                        "contract_version": 1,
                        "workload": "cricket-indexer",
                        "run_id": row["run_id"],
                        **{
                            k: readback[k]
                            for k in ("album", "asset", "revision", "digest")
                        },
                        "vocabulary_release": doc["metadata"]["vocabulary_release"],
                        "collection": "contexts",
                        "uid": uid,
                        "evidence_ref": "cricket-publication/" + identity,
                    }
                    checked = check([reference], [readback], self.definition)
                self._current(db, row)
                now = time.time_ns()
                receipt = {
                    "reference": reference,
                    "readback": readback,
                    "check": checked,
                    "verified_ns": now,
                    "host": self.telemetry.host if self.telemetry else None,
                }
                db.execute(
                    "UPDATE cricket_publication SET state='verified',error=NULL,revision=?,receipt=?,verified_ns=? WHERE id=?",
                    (committed[0], encoded(receipt), now, identity),
                )
                db.execute(
                    "INSERT OR IGNORE INTO cricket_verified_source VALUES(?,?,?,?,?)",
                    (
                        row["completion_key"],
                        identity,
                        row["run_id"],
                        row["backend"],
                        now,
                    ),
                )
                return receipt
        except Exception as error:
            with self.ledger.connect(True) as db:
                db.execute(
                    "UPDATE cricket_publication SET state=CASE WHEN ? THEN 'conflict' WHEN attempts>=3 THEN 'error' ELSE 'pending' END,error=? WHERE id=? AND state!='verified'",
                    (
                        isinstance(error, (Conflict, ValueError)),
                        type(error).__name__,
                        identity,
                    ),
                )
            raise

    def export(self, run_id: str, output: Path) -> dict:
        """Export saved independent readbacks; never reconstruct them from producer JSON."""
        with self.ledger.connect() as db:
            rows = db.execute(
                "SELECT * FROM cricket_publication WHERE run_id=? AND state='verified' ORDER BY verified_ns,id",
                (run_id,),
            ).fetchall()
            receipts = []
            for raw in rows:
                row = dict(raw)
                # Keep append-only receipts, but do not expose stale facts as current.
                try:
                    self._current(db, row)
                except Conflict:
                    continue
                receipts.append(json.loads(row["receipt"]))
            count = db.execute(
                "SELECT COUNT(*) FROM cricket_verified_source WHERE run_id=?", (run_id,)
            ).fetchone()[0]
        if not receipts:
            raise ValueError("No current verified publications for this run")
        references = [r["reference"] for r in receipts]
        readbacks = {
            (
                r["readback"]["album"],
                r["readback"]["asset"],
                r["readback"]["revision"],
            ): r["readback"]
            for r in receipts
        }
        result = check(references, list(readbacks.values()), self.definition)
        output.mkdir(mode=0o700, parents=True, exist_ok=False)
        # A bundle is complete only when its summary is present.
        for name, values in (
            ("media-observations.jsonl", references),
            ("scene-readback.jsonl", list(readbacks.values())),
        ):
            path = output / name
            save_private(path, {})
            path.write_text("".join(encoded(v) + "\n" for v in values))
        summary = {
            **result,
            "unique_sources": len({r["asset"] for r in references}),
            "new_production_completions": count,
        }
        save_private(output / "publication-summary.json", summary)
        return summary


def main() -> None:
    """Publish one explicitly scoped completed original using existing libpq setup."""
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("ledger", "evidence", "shared-module", "schema", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("owner", "album", "asset", "version", "run-id", "backend"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--telemetry-session", type=Path)
    args = parser.parse_args()
    import psycopg

    telemetry = None
    if args.telemetry_session:
        from .telemetry import RunTelemetry

        telemetry = RunTelemetry(args.telemetry_session)
    try:
        publisher = Publisher(
            Ledger(args.ledger),
            args.evidence,
            shared_module(args.shared_module),
            args.schema,
            lambda: psycopg.connect(autocommit=True, connect_timeout=10),
            telemetry=telemetry,
        )
        identity = publisher.enqueue(
            args.owner,
            args.album,
            args.asset,
            args.version,
            args.run_id,
            args.backend,
        )
        publisher.deliver(identity)
        summary = publisher.export(args.run_id, args.output)
    finally:
        if telemetry:
            telemetry.shutdown()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger(__name__).info("%s", json.dumps(summary))


if __name__ == "__main__":
    main()
