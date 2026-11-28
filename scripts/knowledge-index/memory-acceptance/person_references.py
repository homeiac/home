"""Keep visual observations anchored to Immich person IDs across name edits."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PersonRef:
    """Resolved person cluster and optional locally supplied display name."""

    person_id: str | None
    fallback: str = ""

    def name(self, names: dict[str, str]) -> str:
        """Prefer the current directory label, including labels added later."""
        return (names.get(self.person_id or "") or "").strip() or self.fallback or "Unnamed person"


def caption_parts(text: str, people: dict[str, PersonRef]) -> list[str | PersonRef]:
    """Keep already-reviewed names as person references within a caption."""
    if not people:
        return [text]
    alternatives = "|".join(re.escape(name) for name in sorted(people, key=len, reverse=True))
    pattern = re.compile(r"(?<!\w)(" + alternatives + r")(?!\w)")
    return [people.get(part, part) for part in pattern.split(text)]


def resolve_caption(parts: list[str | PersonRef], names: dict[str, str]) -> str:
    """Render the same observation with the current display names."""
    return "".join(part.name(names) if isinstance(part, PersonRef) else part for part in parts)
