"""Use observed kit colors and readable jersey numbers as date-bounded supporting clues."""

import datetime as dt
import json
import re

from .ledger import Ledger

COLORS = {
    "black",
    "white",
    "red",
    "blue",
    "navy",
    "green",
    "yellow",
    "orange",
    "purple",
    "grey",
    "gray",
    "maroon",
    "teal",
    "pink",
    "brown",
}


def kit(value: object) -> dict:
    """Keep only bounded visible descriptions; unreadable numbers remain unknown."""
    if not isinstance(value, dict):
        return {"jersey_colors": [], "jersey_number": None}
    colors = value.get("jersey_colors", [])
    colors = (
        sorted({str(c).lower() for c in colors if str(c).lower() in COLORS})[:3]
        if isinstance(colors, list)
        else []
    )
    number = value.get("jersey_number")
    if type(number) is int:
        number = str(number)
    if not isinstance(number, str) or not re.fullmatch(r"\d{1,3}", number):
        number = None
    return {"jersey_colors": colors, "jersey_number": number}


def nearby(
    ledger: Ledger,
    owner: str,
    album: str,
    person: str,
    asset: str,
    context: dict,
    days: int = 30,
) -> list[dict]:
    """Use effective identities and nearby recordings only; corrected-away people never supply kit clues."""
    if context.get("status") != "known" or not 1 <= days <= 90:
        return []
    try:
        recorded = dt.date.fromisoformat(context["recorded_date"])
    except (KeyError, ValueError, TypeError):
        return []
    left = (recorded - dt.timedelta(days=days)).isoformat()
    right = (recorded + dt.timedelta(days=days)).isoformat()
    clues = []
    seen = set()
    with ledger.connect() as db:
        rows = db.execute(
            """SELECT e.asset,e.overrides,e.review_state,p.payload,p.evidence FROM events e
        JOIN proposals p ON p.id=(SELECT max(p2.id) FROM proposals p2 WHERE p2.event=e.id)
        WHERE e.owner=? AND e.album=? AND e.asset<>? AND e.dismissed=0 AND e.review_state<>'superseded'
        AND json_extract(p.evidence,'$.identity_context.recorded_date') BETWEEN ? AND ? ORDER BY p.id DESC""",
            (owner, album, asset, left, right),
        ).fetchall()
    for row in rows:
        evidence = json.loads(row["evidence"])
        data = json.loads(row["payload"])
        overrides = json.loads(row["overrides"])
        trusted = row["review_state"] == "confirmed" or overrides.get("actor") == person
        if overrides.get("actor", data.get("actor")) != person or (
            evidence.get("age_compatibility") == "incompatible" and not trusted
        ):
            continue
        description = kit(evidence.get("subject_kit"))
        if not description["jersey_colors"] and not description["jersey_number"]:
            continue
        key = (
            tuple(description["jersey_colors"]),
            description["jersey_number"],
            row["asset"],
        )
        if key in seen:
            continue
        seen.add(key)
        clues.append(
            {
                **description,
                "recorded_date": evidence["identity_context"]["recorded_date"],
                "identity_basis": "user_confirmed"
                if row["review_state"] == "confirmed"
                or overrides.get("actor") == person
                else evidence.get("identity_basis", "unresolved"),
            }
        )
        if len(clues) == 5:
            break
    return clues
