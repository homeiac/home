"""Gate a named visual action on evidence tied to the same marked subject."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Action:
    """An evidence claim using canonical action wording and marked region IDs."""

    actor: str
    verb: str
    recipient: str | None = None
    object: str | None = None


def publishable_action(
    actor: str,
    confirmed_regions: set[str],
    model_claims: dict[str, Action | None],
    reviewed: Action | None = None,
) -> Action | None:
    """Require a reviewed claim or two agreeing model families.

    Key model claims by model family so repeated attempts cannot corroborate
    one another. Use a region ID for the recipient of a person-to-person
    action, even when that recipient has no confirmed name.
    """
    if actor not in confirmed_regions:
        return None
    if reviewed is not None:
        return reviewed if reviewed.actor == actor and reviewed.verb else None
    claims = [claim for claim in model_claims.values() if claim is not None]
    if len(claims) < 2:
        return None
    first = claims[0]
    if first.actor != actor or not first.verb or any(claim != first for claim in claims[1:]):
        return None
    return first
