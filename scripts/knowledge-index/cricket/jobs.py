"""Lease durable cricket jobs without resetting another worker's in-flight work."""

import json
import time
from pathlib import Path
from uuid import uuid4

from .ledger import Conflict, Ledger, encoded


def claim(
    ledger: Ledger,
    owner: str,
    album: str,
    version: str,
    evidence: Path,
    now: float | None = None,
    allowed: set[str] | None = None,
    trace_context: dict | None = None,
) -> dict | None:
    """Claim one prepared original with a finite lease and bounded retries."""
    now = time.time() if now is None else now
    with ledger.connect(True) as db:
        rows = db.execute(
            "SELECT j.*,a.kind,a.duration,a.fingerprint,a.locator FROM jobs j JOIN assets a ON a.owner=j.owner AND a.id=j.asset "
            "JOIN members m ON m.owner=j.owner AND m.asset=j.asset WHERE m.owner=? AND m.album=? AND j.version=? AND j.stage='analyze' "
            "AND j.state IN ('queued','running') ORDER BY CASE a.kind WHEN 'video' THEN 0 ELSE 1 END,a.duration,j.asset",
            (owner, album, version),
        ).fetchall()
        for row in rows:
            row = dict(row)
            if allowed is not None and row["asset"] not in allowed:
                continue
            checkpoint = json.loads(row["checkpoint"])
            if checkpoint.get("retry_at", 0) > now or (
                row["state"] == "running" and checkpoint.get("lease_until", 0) > now
            ):
                continue
            if not (evidence / (row["asset"] + ".json")).exists():
                continue
            lease = str(uuid4())
            checkpoint.update(lease=lease, lease_until=now + 900)
            if trace_context is not None:
                checkpoint["trace_context"] = trace_context
            db.execute(
                "UPDATE jobs SET state='running',attempts=attempts+1,checkpoint=?,error=NULL WHERE owner=? AND asset=? AND version=? AND stage='analyze'",
                (encoded(checkpoint), owner, row["asset"], version),
            )
            return {
                **row,
                "id": row["asset"],
                "lease": lease,
                "attempts": row["attempts"] + 1,
                "trace_context": trace_context,
            }
    return None


def check_lease(db: object, owner: str, asset: str, version: str, lease: str) -> dict:
    """Fence stale workers before they mutate results or queue state."""
    row = db.execute(
        "SELECT * FROM jobs WHERE owner=? AND asset=? AND version=? AND stage='analyze'",
        (owner, asset, version),
    ).fetchone()
    if (
        row is None
        or row["state"] != "running"
        or json.loads(row["checkpoint"]).get("lease") != lease
    ):
        raise Conflict("Job lease changed")
    return dict(row)


def heartbeat(ledger: Ledger, job: dict, completed_windows: int) -> None:
    """Renew the lease after each checkpointed inference window."""
    with ledger.connect(True) as db:
        row = check_lease(db, job["owner"], job["asset"], job["version"], job["lease"])
        checkpoint = json.loads(row["checkpoint"])
        checkpoint.update(
            lease_until=time.time() + 900, completed_windows=completed_windows
        )
        db.execute(
            "UPDATE jobs SET checkpoint=? WHERE owner=? AND asset=? AND version=? AND stage='analyze'",
            (encoded(checkpoint), job["owner"], job["asset"], job["version"]),
        )


def failed(ledger: Ledger, job: dict, error: str) -> None:
    """Keep successful window caches and retry a failed asset at most three times."""
    with ledger.connect(True) as db:
        row = check_lease(db, job["owner"], job["asset"], job["version"], job["lease"])
        checkpoint = json.loads(row["checkpoint"])
        checkpoint.update(retry_at=time.time() + 60, lease_until=0)
        db.execute(
            "UPDATE jobs SET state=?,error=?,checkpoint=? WHERE owner=? AND asset=? AND version=? AND stage='analyze'",
            (
                "error" if row["attempts"] >= 3 else "queued",
                error[:300],
                encoded(checkpoint),
                job["owner"],
                job["asset"],
                job["version"],
            ),
        )
