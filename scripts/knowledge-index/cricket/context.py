"""Reuse existing scene captions as explicit best-effort role hints, never face evidence."""

import argparse
import json
import logging
import re
from pathlib import Path

from .prepare import save_preview, save_private


def role_hint(summary: str) -> str | None:
    """Prefer an explicit featured player; ambiguous mentions do not choose a role."""
    text = summary.casefold()
    if not re.search(r"\b(cricket|batter|batting|bowler|bowling|batsman)\b", text):
        return None
    batting = bool(
        re.search(r"\b(batter|batting|batsman|holding a (cricket )?bat)\b", text)
    )
    bowling = bool(
        re.search(
            r"\b(bowler|bowling|bowls|releases? (a|the) ball|delivers? (a|the) ball)\b",
            text,
        )
    )
    if batting and bowling:
        match = re.search(
            r"\b(main subject|focus(?:es)? on|features? a|young (?:boy|girl))\b[^.!?]{0,100}\b(batter|batting|bowler|bowling)\b",
            text,
        )
        if match:
            return "batting" if match[2] in {"batter", "batting"} else "bowling"
        return None
    return "batting" if batting else "bowling" if bowling else None


def apply_hint(raw: dict, summary: str, default_batter: str) -> dict:
    """A low-confidence, actionless role can use a prior caption, visibly marked as a suggestion."""
    hint = role_hint(summary)
    if (
        hint is None
        or raw["data"]["outcome"] not in {"unknown", "other"}
        or raw["data"]["delivery_start"] is not None
    ):
        return raw
    if raw["evidence"].get("confidence") == "likely" and raw["data"]["role"] == hint:
        return raw
    raw["data"]["role"] = hint
    raw["data"]["actor"] = default_batter if hint == "batting" else None
    raw["evidence"]["identity_basis"] = (
        "user_album_rule" if hint == "batting" else "unresolved"
    )
    raw["evidence"]["role_basis"] = "existing_scene_caption"
    raw["evidence"]["confidence"] = "possible"
    raw["evidence"]["reason"] = (
        "Likely "
        + hint
        + " from the existing scene caption; delivery result and timing remain unclear."
    )
    return raw


def main() -> None:
    """Attach captions to cached evidence without decoding originals again."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--folder", type=Path, required=True)
    args = parser.parse_args()
    runtime = json.loads(args.runtime.read_text())
    updated = 0
    for path in args.folder.glob("*.json"):
        value = json.loads(path.read_text())
        summary = runtime["audio"].get(value["asset"], {}).get("visual_summary") or ""
        save_preview(args.folder, {"id": value["asset"]}, value)
        if all(w.get("context_summary") == summary for w in value["windows"]):
            continue
        for window in value["windows"]:
            window["context_summary"] = summary
        save_private(path, value)
        updated += 1
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger(__name__).info(
        "Attached cached captions to %s prepared assets", updated
    )


if __name__ == "__main__":
    main()
