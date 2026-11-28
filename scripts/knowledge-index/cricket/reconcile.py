"""Match deliveries across analysis runs without moving or erasing human corrections."""

import json
import math
from uuid import uuid4

from .jobs import check_lease
from .ledger import Conflict, Ledger, encoded, validate


def anchor(item: dict) -> float | None:
    """Use the observed delivery, never padded or manually edited clip bounds."""
    return item["data"].get("delivery_start")


def same_delivery(first: dict, second: dict) -> bool:
    """Conservative matching tolerates timing jitter but keeps distinct balls separate."""
    a, b = anchor(first), anchor(second)
    if a is not None and b is not None:
        return abs(a - b) <= 2
    if (a is None) != (b is None):
        return False
    left = max(first["observed_start"], second["observed_start"])
    right = min(first["observed_end"], second["observed_end"])
    span = max(
        first["observed_end"] - first["observed_start"],
        second["observed_end"] - second["observed_start"],
    )
    return first["data"]["role"] == second["data"]["role"] and (
        span == 0 or max(0, right - left) / span >= 0.6
    )


def deduplicate(items: list[dict]) -> list[dict]:
    """Fold overlapping-window repeats without merging adjacent deliveries' pre-roll."""
    result = []
    for item in sorted(items, key=lambda p: (p["observed_start"], p["observed_end"])):
        prior = next((p for p in result if same_delivery(p, item)), None)
        if prior is None:
            result.append(json.loads(encoded(item)))
            continue
        a, b = prior["data"]["outcome"], item["data"]["outcome"]
        if {a, b} == {"four", "six"}:
            prior["data"]["outcome"] = "boundary_unclear"
            prior["evidence"]["confidence"] = "possible"
            prior["evidence"]["reason"] = (
                "Overlapping observations disagree about four versus six."
            )
        elif a == "unknown" and b != "unknown":
            result[result.index(prior)] = json.loads(encoded(item))
    return result


def reconcile(
    ledger: Ledger,
    owner: str,
    album: str,
    asset_id: str,
    fingerprint: str,
    items: list[dict],
    *,
    model: str,
    version: str,
    run: str,
    lease: str | None = None,
) -> dict:
    """Commit a whole source result atomically; ambiguous matches stay for review."""
    candidates = deduplicate(items)
    summary = {
        "new": 0,
        "updated": 0,
        "ambiguous": 0,
        "incompatible": 0,
        "superseded": 0,
    }
    with ledger.connect(True) as db:
        if lease is not None:
            check_lease(db, owner, asset_id, version, lease)
        source = ledger._asset(db, owner, album, asset_id)
        if source["fingerprint"] != fingerprint:
            raise Conflict("Source changed during analysis")
        existing = []
        for row in db.execute(
            "SELECT * FROM events WHERE owner=? AND album=? AND asset=?",
            (owner, album, asset_id),
        ).fetchall():
            row = dict(row)
            p = db.execute(
                "SELECT * FROM proposals WHERE event=? ORDER BY id DESC LIMIT 1",
                (row["id"],),
            ).fetchone()
            data = json.loads(p["payload"]) if p else json.loads(row["overrides"])
            evidence = json.loads(p["evidence"]) if p else {}
            existing.append(
                {
                    "row": row,
                    "data": data,
                    "observed_start": evidence.get(
                        "observed_start",
                        data.get("delivery_start") or data.get("start") or 0,
                    ),
                    "observed_end": evidence.get(
                        "observed_end", data.get("outcome_end") or data.get("end") or 0
                    ),
                }
            )
        matches = [
            [i for i, old in enumerate(existing) if same_delivery(old, item)]
            for item in candidates
        ]
        touched = set()
        for item, matched in zip(candidates, matches):
            validate(item["data"], source)
            if not all(
                math.isfinite(item[k]) and item[k] >= 0
                for k in ("observed_start", "observed_end")
            ):
                raise ValueError("Invalid observed interval")
            if len(matched) > 1 or any(
                sum(index in m for m in matches) > 1 for index in matched
            ):
                summary["ambiguous"] += 1
                touched.update(matched)
                continue
            evidence = {
                **item["evidence"],
                "observed_start": item["observed_start"],
                "observed_end": item["observed_end"],
            }
            if matched:
                index = matched[0]
                touched.add(index)
                row = existing[index]["row"]
                event = row["id"]
                try:
                    validate({**item["data"], **json.loads(row["overrides"])}, source)
                except ValueError:
                    summary["incompatible"] += 1
                    continue
                previous = db.execute(
                    "SELECT payload,evidence,model,version FROM proposals WHERE event=? AND run=?",
                    (event, run),
                ).fetchone()
                values = (encoded(item["data"]), encoded(evidence), model, version)
                if previous:
                    if tuple(previous) != values:
                        raise Conflict(
                            "Analysis run already exists with different observations"
                        )
                    continue
                summary["updated"] += 1
            else:
                event = str(uuid4())
                db.execute(
                    "INSERT INTO events(id,owner,album,asset,fingerprint) VALUES(?,?,?,?,?)",
                    (event, owner, album, asset_id, fingerprint),
                )
                summary["new"] += 1
            db.execute(
                "INSERT INTO proposals(event,payload,evidence,model,version,run) VALUES(?,?,?,?,?,?)",
                (event, encoded(item["data"]), encoded(evidence), model, version, run),
            )
            db.execute(
                "UPDATE events SET revision=revision+1,review_state=CASE WHEN review_state='superseded' THEN 'suggested' ELSE review_state END WHERE id=?",
                (event,),
            )
        for index, old in enumerate(existing):
            row = old["row"]
            reviewed = db.execute(
                "SELECT 1 FROM revisions WHERE event=? LIMIT 1", (row["id"],)
            ).fetchone()
            if (
                index not in touched
                and not reviewed
                and not row["manual"]
                and not row["dismissed"]
                and row["review_state"] != "superseded"
            ):
                db.execute(
                    "UPDATE events SET review_state='superseded',revision=revision+1 WHERE id=?",
                    (row["id"],),
                )
                summary["superseded"] += 1
        if lease is not None:
            db.execute(
                "UPDATE jobs SET state='complete',checkpoint=?,error=NULL WHERE owner=? AND asset=? AND version=? AND stage='analyze'",
                (encoded({"run": run, "result": summary}), owner, asset_id, version),
            )
    return summary
