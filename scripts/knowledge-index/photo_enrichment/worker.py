"""Resumable, bounded background extraction with durable per-file retry backoff."""
import logging
from pathlib import Path
import signal
import threading
import time

from .faces import MODEL_ID, FaceEngine
from .metadata import VERSION
from .store import Store


def pending(store: Store, limit: int, timezone: str, faces: bool, now: float) -> list[dict]:
    """Select unfinished current catalog entries; failed files cannot starve the queue."""
    store.db.execute("""CREATE TABLE IF NOT EXISTS worker_attempts (
        path VARCHAR PRIMARY KEY, size_bytes BIGINT, version VARCHAR, model VARCHAR,
        timezone VARCHAR, attempts INTEGER, retry_after DOUBLE)""")
    with store.metrics.measure("queue"):
        return store.rows("""SELECT m.path, m.size_bytes FROM enriched_media m
            LEFT JOIN extracted e ON e.path=m.path AND e.size_bytes=m.size_bytes
            LEFT JOIN face_scans f ON f.path=m.path AND f.size_bytes=m.size_bytes AND f.model=?
            LEFT JOIN worker_attempts a ON a.path=m.path AND a.size_bytes=m.size_bytes
                AND a.version=? AND a.model=? AND a.timezone=?
            WHERE NOT EXISTS (SELECT 1 FROM catalog.gphotos_album_dup d WHERE d.path=m.path)
              AND (e.path IS NULL OR e.error IS NOT NULL OR e.version<>?
                   OR (e.capture_source LIKE 'exif.assumed:%' AND e.capture_source<>?)
                   OR (? AND f.path IS NULL))
              AND (a.retry_after IS NULL OR a.retry_after<=?)
            ORDER BY coalesce(a.attempts,0), m.path LIMIT ?""",
            [MODEL_ID, VERSION, MODEL_ID if faces else "", timezone, VERSION,
             "exif.assumed:" + timezone, faces, now, limit])


def batch(store: Store, engine, limit: int, timezone: str, retry_seconds: float = 3600,
          now: float | None = None) -> dict:
    """Persist progress and retry state before publishing a Parquet snapshot."""
    now = time.time() if now is None else now
    selected = pending(store, limit, timezone, engine is not None, now)
    if not selected:
        store.refresh_metrics()
        # Repair a snapshot if the previous process stopped after its DB commit.
        store.export()
        return {"selected": 0, "processed": 0, "faces": 0, "errors": 0}
    result = store.extract([r["path"] for r in selected], timezone, engine)
    failed = {error["path"] for error in result["errors"]}
    with store.metrics.measure("persist"):
        for row in selected:
            if row["path"] in failed:
                store.db.execute("""INSERT INTO worker_attempts VALUES (?,?,?,?,?,1,?)
                    ON CONFLICT(path) DO UPDATE SET size_bytes=excluded.size_bytes,
                    version=excluded.version, model=excluded.model, timezone=excluded.timezone,
                    attempts=worker_attempts.attempts+1, retry_after=excluded.retry_after""",
                    [row["path"], row["size_bytes"], VERSION, MODEL_ID if engine else "", timezone,
                     now + retry_seconds])
            else:
                store.db.execute("DELETE FROM worker_attempts WHERE path=?", [row["path"]])
    store.export()
    # Logs contain aggregate counts only, never private filenames or face identities.
    return {"selected": len(selected), "processed": result["processed"],
            "faces": result["faces"], "errors": len(failed)}


def run(index: Path, library: Path, state: Path, models: Path, metrics,
        batch_size: int = 25, timezone: str = "UTC", faces: bool = True,
        pause_seconds: float = 2, idle_seconds: float = 60, max_batches: int = 0) -> None:
    """Keep telemetry alive; release both DB handles between batches for other readers."""
    stop = threading.Event()
    previous = {sig: signal.signal(sig, lambda *_: stop.set()) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        engine = None
        if faces:
            import cv2
            cv2.setNumThreads(2)
            with metrics.measure("faces"):
                engine = FaceEngine(models)
        completed = 0
        while not stop.is_set():
            # Reopening picks up catalog rebuilds and avoids holding its read lock while idle.
            store = Store(index, library, state, metrics)
            try:
                store.db.execute("SET threads=2")
                store.db.execute("SET memory_limit='512MB'")
                store.refresh_metrics()
                result = batch(store, engine, batch_size, timezone)
                logging.info("Photo batch: %s", result)
            finally:
                store.close()
            completed += 1
            if max_batches and completed >= max_batches:
                return
            stop.wait(pause_seconds if result["selected"] else idle_seconds)
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
