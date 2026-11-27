"""Publish effective cricket moments into the existing immutable analytical search index."""

import json
from pathlib import Path
from urllib.parse import urlencode

from .ledger import Ledger


def categories(data: dict, default_batter: str | None) -> list[str]:
    """Saved Adil filters are based on the corrected actor, role, and result."""
    if not default_batter or data["actor"] != default_batter:
        return []
    role, outcome = data["role"], data["outcome"]
    result = [role] if role in {"batting", "bowling"} else []
    if role == "batting" and outcome in {"four", "six", "boundary_unclear"}:
        result.append(outcome)
    if outcome in {"dismissal", "run_out"} and role in {"batting", "bowling"}:
        result.append("batting_out" if role == "batting" else "bowling_wicket")
    return result


def rows(
    ledger: Ledger, people: dict, owner: str | None = None, album: str | None = None
) -> list[dict]:
    """Capture one coherent SQLite read transaction, including corrected and manual events."""
    result = []
    with ledger.connect() as db:
        for raw in db.execute(
            "SELECT e.* FROM events e WHERE dismissed=0 AND review_state<>'superseded' AND (? IS NULL OR owner=?) AND (? IS NULL OR album=?) ORDER BY id",
            (owner, owner, album, album),
        ).fetchall():
            event = ledger._effective(db, dict(raw))
            data = event["data"]
            default = db.execute(
                "SELECT default_batter FROM albums WHERE owner=? AND id=?",
                (event["owner"], event["album"]),
            ).fetchone()[0]
            source = ledger._asset(db, event["owner"], event["album"], event["asset"])
            label = people.get(data["actor"], "Person unclear")
            filters = categories(data, default)
            query = urlencode({"album": event["album"], "event": event["id"]})
            result.append(
                {
                    "event": event["id"],
                    "owner": event["owner"],
                    "album": event["album"],
                    "asset": event["asset"],
                    "path": source["locator"],
                    "kind": source["kind"],
                    "revision": event["revision"],
                    "actor": data["actor"],
                    "person": label,
                    "role": data["role"],
                    "outcome": data["outcome"],
                    "wicket_credit": data["wicket_credit"],
                    "start_seconds": data["start"],
                    "end_seconds": data["end"],
                    "review_state": event["review_state"],
                    "categories": filters,
                    "highlight_url": "https://photos.app.home.panderosystems.com/cricket?"
                    + query,
                    "original_url": "https://photos.app.home.panderosystems.com/api/cricket/media?"
                    + urlencode({"album": event["album"], "asset": event["asset"]}),
                    "search_text": " ".join(
                        [
                            label,
                            data["role"],
                            data["outcome"].replace("_", " "),
                            *filters,
                            event["review_state"],
                            event["evidence"].get("reason", ""),
                        ]
                    ).casefold(),
                }
            )
    return result


def search(
    ledger: Ledger,
    people: dict,
    owner: str,
    album: str,
    query: str = "",
    category: str = "all",
) -> list[dict]:
    """Read authoritative effective results so a correction changes filters immediately."""
    if len(query) > 200:
        raise ValueError("Search text too long")
    if category not in {
        "all",
        "batting",
        "bowling",
        "four",
        "six",
        "boundary_unclear",
        "batting_out",
        "bowling_wicket",
    }:
        raise ValueError("Unknown cricket filter")
    return [
        r
        for r in rows(ledger, people, owner, album)
        if (category == "all" or category in r["categories"])
        and all(term in r["search_text"] for term in query.casefold().split())
    ]


def build_index(db: object, directory: Path, state: Path) -> None:
    """Write a complete replacement table; removals cannot linger in append-only batches."""
    records = []
    if (state / "ledger.sqlite3").is_file():
        people = (
            json.loads((state / "people.json").read_text())
            if (state / "people.json").exists()
            else {}
        )
        records = rows(Ledger(state / "ledger.sqlite3"), people)
    db.execute(
        "CREATE TEMP TABLE idx_cricket_highlights(event VARCHAR,owner VARCHAR,album VARCHAR,asset VARCHAR,path VARCHAR,kind VARCHAR,revision BIGINT,actor VARCHAR,person VARCHAR,role VARCHAR,outcome VARCHAR,wicket_credit VARCHAR,start_seconds DOUBLE,end_seconds DOUBLE,review_state VARCHAR,categories VARCHAR[],highlight_url VARCHAR,original_url VARCHAR,search_text VARCHAR)"
    )
    if records:
        db.executemany(
            "INSERT INTO idx_cricket_highlights VALUES (" + ",".join(["?"] * 19) + ")",
            [list(r.values()) for r in records],
        )
    target = str(directory / "cricket_highlights.parquet").replace("'", "''")
    db.execute(
        "COPY idx_cricket_highlights TO '"
        + target
        + "' (FORMAT parquet, COMPRESSION zstd)"
    )
