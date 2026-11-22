#!/usr/bin/env python3
"""Save private Photos review preferences from a JSON object on stdin."""
import json
import sys

from photo_enrichment.postgres import connect


def names(values: list[str], *, normalize: bool = False) -> list[str]:
    """Validate and deduplicate display names or normalized match keys."""
    if not isinstance(values, list) or any(not isinstance(v, str) or not 1 <= len(v.strip()) <= 200 for v in values):
        raise ValueError('Expected a list of names')
    return list(dict.fromkeys(v.strip().lower() if normalize else v.strip() for v in values))


def main() -> None:
    raw = json.load(sys.stdin)
    settings = dict(people=names(raw['people'], normalize=True), pets=names(raw.get('pets', [])))
    with connect() as connection:
        connection.execute("""INSERT INTO pipeline_state VALUES ('priority_review',%s,now())
            ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=now()""",[json.dumps(settings)])
    print(f"Saved {len(settings['people'])} priority people and {len(settings['pets'])} pet searches")


if __name__ == '__main__':
    main()
