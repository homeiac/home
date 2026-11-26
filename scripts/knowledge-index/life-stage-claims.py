"""Reserve the tail of the local life-stage queue for an additional worker."""

import sqlite3


def initialize(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS rtx_life_stage_claims "
        "(asset TEXT PRIMARY KEY, state TEXT NOT NULL)"
    )


def claim(conn: sqlite3.Connection, mac_batch: int = 16) -> tuple[str, str] | None:
    """Reserve one tail item beyond the Mac's maximum in-flight head batch."""
    conn.execute("BEGIN IMMEDIATE")
    with conn:
        reserved = conn.execute(
            "SELECT j.asset, j.input FROM jobs j JOIN rtx_life_stage_claims c USING(asset) "
            "WHERE j.status = 'running' AND c.state = 'active' LIMIT 1"
        ).fetchone()
        if reserved is not None:
            return reserved
        # The Mac worker reads its next batch without marking those rows active.
        # Keep a cushion beyond its entire batch while the two readers overlap.
        if conn.execute("SELECT count(*) FROM jobs WHERE status='pending'").fetchone()[0] <= 2 * mac_batch:
            return None
        row = conn.execute(
            "SELECT asset, input FROM jobs WHERE status='pending' "
            "AND asset NOT IN (SELECT asset FROM rtx_life_stage_claims) "
            "AND asset NOT IN (SELECT asset FROM jobs WHERE status='pending' "
            "ORDER BY day, asset LIMIT ?) "
            "ORDER BY day DESC, asset DESC LIMIT 1",
            (mac_batch,),
        ).fetchone()
        if row is None:
            return None
        asset, _ = row
        conn.execute("UPDATE jobs SET status='running' WHERE asset=?", (asset,))
        conn.execute("INSERT INTO rtx_life_stage_claims VALUES (?, 'active')", (asset,))
        return row


def finish(conn: sqlite3.Connection, asset: str, status: str, outcome: str | None) -> None:
    """Commit an RTX result or release the item for the Mac without re-claiming it."""
    if status not in {"pending", "complete", "withheld"}:
        raise ValueError("Unexpected RTX disposition")
    with conn:
        updated = conn.execute(
            "UPDATE jobs SET status=?, outcome=? WHERE asset=? AND status='running' "
            "AND EXISTS (SELECT 1 FROM rtx_life_stage_claims WHERE asset=? AND state='active')",
            (status, outcome, asset, asset),
        )
        if updated.rowcount != 1:
            raise RuntimeError("RTX reservation changed")
        conn.execute(
            "UPDATE rtx_life_stage_claims SET state=? WHERE asset=?",
            ("released" if status == "pending" else status, asset),
        )
