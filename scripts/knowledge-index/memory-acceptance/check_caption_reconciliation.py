"""Check two cold runs against private fact expectations without printing any captions.

The private JSON file maps asset UUIDs to required and forbidden regexes. Use separate
output directories for the same jobs and model configuration. Patterns describe the facts
in the independent review and may allow several ways of expressing them.
"""

import argparse
import json
from pathlib import Path
import re
from uuid import UUID


def check(expected: dict, runs: list[Path]) -> None:
    """Require complete coverage and the same reviewed facts in each fresh output."""
    if not expected or len(set(path.resolve() for path in runs)) < 2:
        raise ValueError("Provide a private fact set and distinct run directories")
    for run in runs:
        if {path.stem for path in run.glob("*.json")} != set(expected):
            raise ValueError("Model outputs differ from the expected evaluation scope")
    for index, (asset, rules) in enumerate(expected.items(), start=1):
        if not rules.get("required"):
            raise ValueError(f"Case {index} has no positive control")
        hashes = set()
        for run in runs:
            row = json.loads((run / (str(UUID(asset)) + ".json")).read_text())
            hashes.add(row["input_hash"])
            caption = row.get("caption", "")
            valid = (row.get("status") == "proposed"
                     and all(re.search(pattern, caption, re.I) for pattern in rules["required"])
                     and not any(re.search(pattern, caption, re.I) for pattern in rules["forbidden"]))
            if not valid:
                raise ValueError(f"Case {index} failed its factual checks in run {runs.index(run) + 1}")
        if len(hashes) != 1:
            raise ValueError(f"Case {index} used different inputs or settings")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("expectations", type=Path)
    parser.add_argument("runs", type=Path, nargs="+")
    args = parser.parse_args()
    cases = json.loads(args.expectations.read_text())
    check(cases, args.runs)
    print(f"{len(cases)} cases passed factual checks across {len(args.runs)} runs")
