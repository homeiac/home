"""Persistent reuse of successful captions for identical model inputs.

Paths are deliberately excluded, but prompt context, image bytes, model and
inference settings must match. No filename/size heuristic can cause a hit.
"""
import hashlib
import json
import sqlite3
from pathlib import Path


class SummaryCache:
    """Store only parsed successful answers; survive batch retries and restarts."""

    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute("CREATE TABLE IF NOT EXISTS answers (key TEXT PRIMARY KEY, answer TEXT NOT NULL)")

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
        row = self.connection.execute("SELECT answer FROM answers WHERE key=?", (key,)).fetchone()
        if row is None:
            return None
        summary, tags = json.loads(row[0])
        return summary, tags

    def put(self, key: str, summary: str, tags: list[str]) -> None:
        """Atomically save a successful parsed answer, independently of Parquet batches."""
        with self.connection:
            self.connection.execute("INSERT OR IGNORE INTO answers VALUES (?, ?)",
                                    (key, json.dumps([summary, tags])))

    def close(self) -> None:
        """Release the connection."""
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
