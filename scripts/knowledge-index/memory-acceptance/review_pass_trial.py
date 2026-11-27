"""Blind the saved action statements, then score both arms from one visual review."""

import argparse
import json
from pathlib import Path
from itertools import product

from tune_library_worker import summarize


def compare(
    folder: Path, ratings: dict[str, bool] | None = None, mirror: Path | None = None
) -> dict:
    """Check the paired frames, hide mode labels, and count whole supported actions."""
    rows = json.loads((folder / "sample.json").read_text())
    folders = [folder]
    if mirror:
        if json.loads((mirror / "sample.json").read_text()) != rows:
            raise ValueError("Counterbalanced block used different faces")
        folders.append(mirror)
    summary = {}
    hashes = {}
    arms = {}
    statements = set()
    for backend in ("mac-metal", "rtx3070"):
        for arm in ("baseline", "candidate"):
            name = f"{backend}/{arm}"
            readings = []
            runs = []
            for block, repeat in product(folders, (1, 2)):
                report = json.loads(
                    (block / f"{backend}-{arm}-{repeat}.json").read_text()
                )
                runs.append(report)
                items = report["results"]
                if sorted(item["index"] for item in items) != list(range(len(rows))):
                    raise ValueError("Repeat does not cover the fixed sample")
                for item in items:
                    index = item["index"]
                    pair = item["frame_hashes"]
                    if len(pair) != 2 or hashes.setdefault(index, pair) != pair:
                        raise ValueError("Face inputs differed across arms")
                    if item["state"] == "complete":
                        statements.add((index, item["outcome"]["action"]))
                readings.extend(items)
            arms[name] = readings
            summary[name] = summarize(runs, rows)

    questions = {}
    labels = {}
    for index, action in sorted(statements):
        options = questions.setdefault(index, [])
        key = f"{index}-{len(options)}"
        labels[index, action] = key
        options.append({"key": key, "action": action})
    if ratings is None:
        return questions
    if ratings.keys() != set(labels.values()) or any(
        type(v) is not bool for v in ratings.values()
    ):
        raise ValueError("Supply one boolean visual rating for every action")
    for name, items in arms.items():
        supported = [
            r
            for r in items
            if r["state"] == "complete"
            and ratings[labels[r["index"], r["outcome"]["action"]]]
        ]
        exact_stages = 0
        for r in items:
            expected = rows[r["index"]][1]
            age = r.get("raw_age", r.get("raw_joint", {}))
            if (
                expected
                and age.get("confidence") in {"medium", "high"}
                and age.get("stage") == expected
            ):
                exact_stages += 1
        summary[name].update(
            reviewed_stage_exact=exact_stages,
            supported_actions=len(supported),
            both_correct=sum(
                rows[r["index"]][1] == r["outcome"]["stage"] for r in supported
            ),
            inference_calls=sum(
                k in item
                for item in items
                for k in ("age_seconds", "action_seconds", "joint_seconds")
            ),
        )
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument(
        "--ratings",
        type=Path,
        help="Private JSON mapping each review key to true or false",
    )
    parser.add_argument(
        "--mirror", type=Path, help="Second block run with --joint-first"
    )
    args = parser.parse_args()
    print(
        json.dumps(
            compare(
                args.folder,
                json.loads(args.ratings.read_text()) if args.ratings else None,
                args.mirror,
            ),
            indent=2,
        )
    )
