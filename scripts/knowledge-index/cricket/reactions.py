"""Nominate best-effort outcomes from timed reactions when visual evidence identifies cricket."""

import re

from .analyze import proposal


def outcome(text: str) -> str | None:
    """Prefer explicit reactions and ignore obvious instructions, questions, and negations."""
    text = text.casefold()
    runout = bool(re.search(r"\brun[ -]?out\b", text))
    if (
        runout
        and "?" not in text
        and not re.search(r"\b(not|no) (a |an )?(failed|unsuccessful|missed)\b", text)
        and re.search(
            r"\bnot out\b|\b(failed|unsuccessful|missed) run[ -]?out\b|\brun[ -]?out attempt (failed|missed)\b",
            text,
        )
    ):
        return "attempted_run_out"
    if re.search(
        r"\b(go for|hit (a|another)|need|want|almost|nearly|not|no|is (he|that)|howzat|appeal)\b|\?",
        text,
    ):
        return None
    # Spectators can be appealing or describing an attempt. Audio alone cannot
    # establish whether the featured batter was actually dismissed.
    if runout:
        return None
    if re.search(
        r"\b(bowled (him|her)|caught (him|her)|he'?s out|he is out|wicket)\b", text
    ):
        return None
    four = bool(re.search(r"\b(four|4)\b|चौका", text))
    six = bool(re.search(r"\b(six|6)\b|छक्का", text))
    return (
        "boundary_unclear"
        if four and six
        else "four"
        if four
        else "six"
        if six
        else None
    )


def supplement(
    items: list[dict], asset: dict, window: dict, default_batter: str
) -> list[dict]:
    """Use reactions as possible suggestions, never as identity proof or photo outcomes."""
    if asset["kind"] != "video":
        return items
    roles = {
        p["data"]["role"] for p in items if p["data"]["role"] in {"batting", "bowling"}
    }
    if len(roles) != 1:
        return items
    role = next(iter(roles))
    template = next(p for p in items if p["data"]["role"] == role)
    result = list(items)
    for segment in window["audio"]["segments"]:
        label = outcome(segment["text"])
        if label is None:
            continue
        at = max(window["start"], min(window["end"], segment["end"]))
        if any(
            p["data"]["outcome"] not in {"unknown", "other"}
            and abs((p["data"].get("outcome_end") or at) - at) < 5
            for p in items
        ):
            continue
        candidate = proposal(
            {
                "role": role,
                "actor": "unknown",
                "featured_batter": False,
                "outcome": label,
                "wicket_credit": "unknown",
                "release": None,
                "outcome_end": at,
                "confidence": "possible",
                "reason": "Possible "
                + label.replace("_", " ")
                + " from a timed spectator reaction; outcome and timing may need correction.",
            },
            asset,
            window,
            default_batter,
        )
        candidate["data"]["actor"] = template["data"]["actor"]
        candidate["data"]["start"] = max(0, at - 15)
        candidate["evidence"]["identity_basis"] = template["evidence"]["identity_basis"]
        candidate["evidence"]["result_basis"] = "audio_reaction_suggestion"
        candidate["evidence"]["reaction_time"] = at
        candidate["observed_start"] = max(window["start"], at - 5)
        result.append(candidate)
    return result
