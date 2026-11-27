"""Private SQLite ledger. Each public operation owns a short transaction."""

import json
import math
import os
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

VERSION = 1
ROLES = {"batting", "bowling", "other", "unknown"}
OUTCOMES = {
    "four",
    "six",
    "boundary_unclear",
    "dismissal",
    "run_out",
    "other",
    "unknown",
}
CREDITS = {"bowler", "run_out", "unknown"}
FIELDS = {
    "actor",
    "role",
    "outcome",
    "wicket_credit",
    "start",
    "end",
    "delivery_start",
    "outcome_end",
}
SCHEMA = """
CREATE TABLE albums (
 owner TEXT NOT NULL, id TEXT NOT NULL, default_batter TEXT,
 provenance TEXT NOT NULL, rule_revision INTEGER NOT NULL DEFAULT 1,
 PRIMARY KEY(owner,id));
CREATE TABLE assets (
 owner TEXT NOT NULL, id TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('photo','video')),
 duration REAL, fingerprint TEXT NOT NULL, locator TEXT NOT NULL,
 PRIMARY KEY(owner,id));
CREATE TABLE members (
 owner TEXT NOT NULL, album TEXT NOT NULL, asset TEXT NOT NULL,
 PRIMARY KEY(owner,album,asset),
 FOREIGN KEY(owner,album) REFERENCES albums(owner,id),
 FOREIGN KEY(owner,asset) REFERENCES assets(owner,id));
CREATE TABLE events (
 id TEXT PRIMARY KEY, owner TEXT NOT NULL, album TEXT NOT NULL, asset TEXT NOT NULL,
 fingerprint TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0,
 overrides TEXT NOT NULL DEFAULT '{}', dismissed INTEGER NOT NULL DEFAULT 0,
 review_state TEXT NOT NULL DEFAULT 'suggested', manual INTEGER NOT NULL DEFAULT 0,
 FOREIGN KEY(owner,album,asset) REFERENCES members(owner,album,asset));
CREATE TABLE proposals (
 id INTEGER PRIMARY KEY, event TEXT NOT NULL REFERENCES events(id), payload TEXT NOT NULL,
 evidence TEXT NOT NULL, model TEXT NOT NULL, version TEXT NOT NULL, run TEXT NOT NULL,
 created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(event,run));
CREATE TABLE revisions (
 id INTEGER PRIMARY KEY, event TEXT NOT NULL REFERENCES events(id), revision INTEGER NOT NULL,
 action TEXT NOT NULL, editor TEXT NOT NULL, before_state TEXT NOT NULL, after_state TEXT NOT NULL,
 created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(event,revision));
CREATE TABLE jobs (
 owner TEXT NOT NULL, asset TEXT NOT NULL, version TEXT NOT NULL, stage TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'queued', checkpoint TEXT NOT NULL DEFAULT '{}',
 attempts INTEGER NOT NULL DEFAULT 0, error TEXT,
 PRIMARY KEY(owner,asset,version,stage), FOREIGN KEY(owner,asset) REFERENCES assets(owner,id));
CREATE INDEX events_album ON events(owner,album);
CREATE INDEX proposals_event ON proposals(event,id);
"""


class Conflict(ValueError):
    """A source or revision changed; the caller must refresh before writing."""


def encoded(value: Any) -> str:
    """Serialize private state with non-finite values rejected."""
    return json.dumps(value, allow_nan=False, sort_keys=True)


def require_text(value: str) -> str:
    """Validate an opaque identifier without assuming UUID-only upstream IDs."""
    if not isinstance(value, str) or not value.strip() or len(value) > 1024:
        raise ValueError("Expected a nonempty identifier")
    return value


def finite(value: Any) -> bool:
    """Whether a value is a finite number rather than a JSON boolean."""
    return type(value) in (int, float) and math.isfinite(value)


def validate(payload: dict, asset: dict) -> None:
    """Validate the complete effective event against its original media."""
    if not isinstance(payload, dict) or set(payload) != FIELDS:
        raise ValueError("Expected complete event fields")
    if payload["actor"] is not None:
        require_text(payload["actor"])
    if (
        not isinstance(payload["role"], str)
        or not isinstance(payload["outcome"], str)
        or payload["role"] not in ROLES
        or payload["outcome"] not in OUTCOMES
    ):
        raise ValueError("Unknown role or outcome")
    if (
        not isinstance(payload["wicket_credit"], str)
        or payload["wicket_credit"] not in CREDITS
    ):
        raise ValueError("Unknown wicket credit")
    if payload["wicket_credit"] == "bowler" and not (
        payload["role"] == "bowling" and payload["outcome"] == "dismissal"
    ):
        raise ValueError("Bowler credit requires a bowling dismissal")
    if payload["wicket_credit"] == "run_out" and payload["outcome"] != "run_out":
        raise ValueError("Run-out credit requires a run-out")
    times = [payload[k] for k in ("start", "end", "delivery_start", "outcome_end")]
    if asset["kind"] == "photo":
        if any(t is not None for t in times) or payload["outcome"] not in {
            "unknown",
            "other",
        }:
            raise ValueError("Photos have roles, not timed delivery outcomes")
        return
    start, end, delivery, outcome = times
    duration = asset["duration"]
    if not finite(start) or not finite(end) or not 0 <= start < end <= duration:
        raise ValueError("Invalid highlight bounds")
    for t in (delivery, outcome):
        if t is not None and (not finite(t) or not 0 <= t <= duration):
            raise ValueError("Invalid event timestamp")
    if delivery is not None and outcome is not None and delivery > outcome:
        raise ValueError("Outcome precedes delivery")


def backup(source: Path, destination: Path) -> None:
    """Take an online consistent backup, refusing to overwrite a previous backup."""
    source, destination = source.resolve(), destination.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    try:
        with (
            closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as src,
            closing(sqlite3.connect(destination)) as dst,
        ):
            src.backup(dst)
            if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Backup failed integrity check")
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def restore(source: Path, destination: Path) -> None:
    """Restore to a new path; switching a running service is a separate operation."""
    with closing(
        sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)
    ) as db:
        if db.execute("PRAGMA user_version").fetchone()[0] != VERSION:
            raise ValueError("Unsupported backup schema")
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Invalid backup")
    backup(source, destination)


class Ledger:
    """Store scoped proposals and immutable correction history on local disk."""

    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        existed = self.path.exists()
        if not existed:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        with self.connect() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > VERSION:
                raise ValueError("Ledger was created by a newer version")
            if version == 0:
                if existed:
                    backup(
                        self.path,
                        self.path.with_name(
                            self.path.name + ".before-v1-" + uuid4().hex
                        ),
                    )
                db.executescript(
                    "BEGIN IMMEDIATE;\n" + SCHEMA + "\nPRAGMA user_version=1; COMMIT;"
                )
            db.commit()
            db.execute("PRAGMA journal_mode=WAL")

    @contextmanager
    def connect(self, write: bool = False) -> Iterator[sqlite3.Connection]:
        """Commit successful operations, roll back failures, and close connections."""
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def add_album(
        self, owner: str, album: str, default_batter: str | None = None
    ) -> None:
        """Register an album without replacing its saved user rule on rediscovery."""
        require_text(owner)
        require_text(album)
        if default_batter is not None:
            require_text(default_batter)
        with self.connect(True) as db:
            db.execute(
                "INSERT OR IGNORE INTO albums(owner,id,default_batter,provenance) VALUES(?,?,?,?)",
                (owner, album, default_batter, "user_album_rule"),
            )

    def add_asset(
        self,
        owner: str,
        album: str,
        asset: str,
        kind: str,
        duration: float | None,
        fingerprint: str,
        locator: str = "",
    ) -> None:
        """Add an original; source changes require explicit remapping of old events."""
        require_text(asset)
        require_text(fingerprint)
        if kind not in {"photo", "video"}:
            raise ValueError("Unknown media kind")
        if (kind == "video" and (not finite(duration) or duration <= 0)) or (
            kind == "photo" and duration is not None
        ):
            raise ValueError("Invalid media duration")
        with self.connect(True) as db:
            old = db.execute(
                "SELECT * FROM assets WHERE owner=? AND id=?", (owner, asset)
            ).fetchone()
            if old and (old["fingerprint"], old["kind"], old["duration"]) != (
                fingerprint,
                kind,
                duration,
            ):
                raise Conflict("Original changed; remap events before replacing it")
            db.execute(
                "INSERT OR IGNORE INTO assets VALUES(?,?,?,?,?,?)",
                (owner, asset, kind, duration, fingerprint, locator),
            )
            db.execute(
                "INSERT OR IGNORE INTO members VALUES(?,?,?)", (owner, album, asset)
            )

    @staticmethod
    def _asset(db: sqlite3.Connection, owner: str, album: str, asset: str) -> dict:
        row = db.execute(
            "SELECT a.* FROM assets a JOIN members m ON a.owner=m.owner AND a.id=m.asset "
            "WHERE m.owner=? AND m.album=? AND m.asset=?",
            (owner, album, asset),
        ).fetchone()
        if row is None:
            raise KeyError("Asset not in this owner's album")
        return dict(row)

    @staticmethod
    def _event(db: sqlite3.Connection, owner: str, event: str) -> dict:
        row = db.execute(
            "SELECT * FROM events WHERE owner=? AND id=?", (owner, event)
        ).fetchone()
        if row is None:
            raise KeyError("Event not found")
        return dict(row)

    @staticmethod
    def _effective(db: sqlite3.Connection, row: dict) -> dict:
        proposal = db.execute(
            "SELECT * FROM proposals WHERE event=? ORDER BY id DESC LIMIT 1",
            (row["id"],),
        ).fetchone()
        payload = json.loads(proposal["payload"]) if proposal else {}
        payload.update(json.loads(row["overrides"]))
        return {
            **row,
            "overrides": json.loads(row["overrides"]),
            "data": payload,
            "evidence": json.loads(proposal["evidence"]) if proposal else {},
            "proposal_version": proposal["version"] if proposal else None,
        }

    def get(self, owner: str, event: str) -> dict:
        """Read one effective event using its owner boundary."""
        with self.connect() as db:
            return self._effective(db, self._event(db, owner, event))

    def list_events(
        self, owner: str, album: str, include_dismissed: bool = False
    ) -> list[dict]:
        """Read a consistent snapshot of album events."""
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM events WHERE owner=? AND album=? AND (? OR dismissed=0) AND review_state<>'superseded' ORDER BY rowid",
                (owner, album, include_dismissed),
            )
            return [self._effective(db, dict(row)) for row in rows]

    def create_event(
        self,
        owner: str,
        album: str,
        asset: str,
        payload: dict,
        *,
        manual: bool = False,
        editor: str = "owner",
    ) -> str:
        """Create a stable event, independent of mutable labels and timestamps."""
        event = str(uuid4())
        with self.connect(True) as db:
            source = self._asset(db, owner, album, asset)
            validate(payload, source)
            db.execute(
                "INSERT INTO events(id,owner,album,asset,fingerprint,overrides,manual,review_state) VALUES(?,?,?,?,?,?,?,?)",
                (
                    event,
                    owner,
                    album,
                    asset,
                    source["fingerprint"],
                    encoded(payload) if manual else "{}",
                    manual,
                    "corrected" if manual else "suggested",
                ),
            )
            if manual:
                row = self._event(db, owner, event)
                self._save_revision(db, row, editor, "create", self._state(row))
            else:
                db.execute(
                    "INSERT INTO proposals(event,payload,evidence,model,version,run) VALUES(?,?,?,?,?,?)",
                    (event, encoded(payload), "{}", "seed", "seed", "seed"),
                )
        return event

    def propose(
        self,
        owner: str,
        event: str,
        payload: dict,
        *,
        evidence: dict,
        model: str,
        version: str,
        run: str,
    ) -> dict:
        """Append a proposal atomically, retaining corrections and idempotent retries."""
        for value in (model, version, run):
            require_text(value)
        with self.connect(True) as db:
            row = self._event(db, owner, event)
            source = self._asset(db, owner, row["album"], row["asset"])
            validate(payload, source)
            validate({**payload, **json.loads(row["overrides"])}, source)
            values = (encoded(payload), encoded(evidence), model, version)
            old = db.execute(
                "SELECT payload,evidence,model,version FROM proposals WHERE event=? AND run=?",
                (event, run),
            ).fetchone()
            if old:
                if tuple(old) != values:
                    raise Conflict("Analysis run already saved different results")
            else:
                db.execute(
                    "INSERT INTO proposals(event,payload,evidence,model,version,run) VALUES(?,?,?,?,?,?)",
                    (event, *values, run),
                )
                db.execute("UPDATE events SET revision=revision+1 WHERE id=?", (event,))
            return self._effective(db, self._event(db, owner, event))

    @staticmethod
    def _state(row: dict) -> dict:
        return {k: row[k] for k in ("overrides", "dismissed", "review_state")}

    @staticmethod
    def _save_revision(
        db: sqlite3.Connection, row: dict, editor: str, action: str, state: dict
    ) -> None:
        require_text(editor)
        revision = row["revision"] + 1
        db.execute(
            "INSERT INTO revisions(event,revision,action,editor,before_state,after_state) VALUES(?,?,?,?,?,?)",
            (
                row["id"],
                revision,
                action,
                editor,
                encoded(Ledger._state(row)),
                encoded(state),
            ),
        )
        db.execute(
            "UPDATE events SET overrides=?,dismissed=?,review_state=?,revision=? WHERE id=?",
            (
                state["overrides"],
                state["dismissed"],
                state["review_state"],
                revision,
                row["id"],
            ),
        )

    def revise(
        self,
        owner: str,
        event: str,
        revision: int,
        *,
        patch: dict | None = None,
        action: str = "edit",
        editor: str = "owner",
    ) -> dict:
        """Apply a correction or undo without deleting any previous revision."""
        if action not in {"edit", "accept", "dismiss", "restore", "undo"}:
            raise ValueError("Unknown revision action")
        if patch is not None and (not isinstance(patch, dict) or set(patch) - FIELDS):
            raise ValueError("Unknown correction fields")
        if action != "edit" and patch:
            raise ValueError("Only edit accepts changed fields")
        with self.connect(True) as db:
            row = self._event(db, owner, event)
            if type(revision) is not int or revision != row["revision"]:
                raise Conflict("Highlight changed; reload before saving")
            state = self._state(row)
            overrides = json.loads(state["overrides"])
            if action == "undo":
                previous = db.execute(
                    "SELECT before_state,action FROM revisions WHERE event=? ORDER BY id DESC LIMIT 1",
                    (event,),
                ).fetchone()
                if previous is None or previous["action"] == "create":
                    raise ValueError(
                        "Nothing to undo; dismiss a manually added highlight to remove it"
                    )
                state = json.loads(previous["before_state"])
            elif action == "accept":
                overrides = self._effective(db, row)["data"]
                state.update(overrides=encoded(overrides), review_state="confirmed")
            elif action in {"dismiss", "restore"}:
                state["dismissed"] = int(action == "dismiss")
            else:
                if not patch:
                    raise ValueError("No correction fields")
                overrides.update(patch)
                state.update(overrides=encoded(overrides), review_state="corrected")
            candidate = {**row, **state}
            validate(
                self._effective(db, candidate)["data"],
                self._asset(db, owner, row["album"], row["asset"]),
            )
            self._save_revision(db, row, editor, action, state)
            return self._effective(db, self._event(db, owner, event))
