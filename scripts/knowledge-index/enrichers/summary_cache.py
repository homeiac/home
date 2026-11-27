"""Persistent reuse of successful captions for identical model inputs.

Paths are deliberately excluded, but prompt context, image bytes, model and
inference settings must match. No filename/size heuristic can cause a hit.
"""
import hashlib
import json
import sqlite3
from pathlib import Path
from threading import Lock


class SummaryCache:
    """Store only parsed successful answers; survive batch retries and restarts."""

    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.lock = Lock()
        self.raw_locks = [Lock() for _ in range(64)]
        self.connection.execute("""CREATE TABLE IF NOT EXISTS raw_answers
            (enricher TEXT, sha256 TEXT, answer TEXT NOT NULL, PRIMARY KEY(enricher,sha256))""")
        self.connection.execute("CREATE TABLE IF NOT EXISTS answers (key TEXT PRIMARY KEY, answer TEXT NOT NULL)")

    def raw_lock(self, fingerprint: str):
        """The Mac and RTX dispatch threads share this worker and cache."""
        return self.raw_locks[int(fingerprint[:2], 16) % len(self.raw_locks)]

    def raw_caption(self, enricher: str, fingerprint: str) -> tuple | None:
        with self.lock:
            row = self.connection.execute("SELECT answer FROM raw_answers WHERE enricher=? AND sha256=?",
                                          (enricher, fingerprint)).fetchone()
        return tuple(json.loads(row[0])) if row else None

    def remember_raw(self, enricher: str, fingerprint: str, summary: str, tags: list, model: str) -> None:
        with self.lock, self.connection:
            self.connection.execute("INSERT OR IGNORE INTO raw_answers VALUES (?, ?, ?)",
                                    (enricher, fingerprint, json.dumps([summary, tags, model])))

    @staticmethod
    def key(prompt: str, images: list[bytes], settings: dict) -> str:
        """Fingerprint exact inputs with unambiguous boundaries and a cache version."""
        digest = hashlib.sha256()
        for part in [b"summary-cache-v1", json.dumps(settings, sort_keys=True, separators=(",", ":")).encode(),
                     prompt.encode(), *images]:
            digest.update(len(part).to_bytes(8, "big"))
            digest.update(part)
        return digest.hexdigest()

    def get(self, key: str) -> tuple[str, list[str]] | None:
        """Return a previously validated answer, if present."""
        with self.lock:
            row = self.connection.execute("SELECT answer FROM answers WHERE key=?", (key,)).fetchone()
        if row is None:
            return None
        summary, tags = json.loads(row[0])
        return summary, tags

    def put(self, key: str, summary: str, tags: list[str]) -> None:
        """Atomically save a successful parsed answer, independently of Parquet batches."""
        with self.lock, self.connection:
            self.connection.execute("INSERT OR IGNORE INTO answers VALUES (?, ?)",
                                    (key, json.dumps([summary, tags])))

    def close(self) -> None:
        """Release the connection."""
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
