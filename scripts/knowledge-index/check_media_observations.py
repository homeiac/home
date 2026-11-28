#!/usr/bin/env python3
"""Check private workload observation references against independent scene-table exports."""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from jsonschema import Draft7Validator, FormatChecker
from jsonschema.exceptions import ValidationError

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = ROOT / "schemas/media-observation-reference.schema.json"
FORMAT = "1.0.0"


def pg_digest(scene: dict) -> str:
    """Match openlabel_album.persist's existing scene serialization, including whitespace."""
    return hashlib.sha256(json.dumps(scene, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def check(references: list, rows: list, definition: dict) -> dict:
    """Validate against readbacks keyed exactly like the shared PostgreSQL writer."""
    if definition["definitions"]["metadata"]["properties"]["schema_version"]["enum"] != [FORMAT]:
        raise ValueError("expected the pinned OpenLABEL 1.0.0 schema")
    scene_validator = Draft7Validator(definition)
    ref_validator = Draft7Validator(json.loads(REFERENCE.read_text()), format_checker=FormatChecker())
    saved = {}
    for row in rows:
        key = row["album"], row["asset"], row["revision"]
        scene = row["scene"]
        if row["digest"] != pg_digest(scene) or key in saved:
            raise ValueError("changed scene digest or duplicate readback key")
        scene_validator.validate(scene)
        graph = scene["openlabel"]
        for relation in graph.get("relations", {}).values():
            for endpoint in relation["rdf_subjects"] + relation["rdf_objects"]:
                if endpoint["uid"] not in graph.get(endpoint["type"] + "s", {}):
                    raise ValueError("relation points to a missing typed occurrence")
        saved[key] = row
    counts = Counter()
    seen = set()
    for ref in references:
        ref_validator.validate(ref)
        key = ref["album"], ref["asset"], ref["revision"]
        row = saved.get(key)
        if row is None or row["digest"] != ref["digest"]:
            raise ValueError("observation reference does not match the saved revision")
        data = row["scene"]["openlabel"]
        meta = data["metadata"]
        if ref["workload"] == "cricket-indexer" and (
            meta.get("producer") != "cricket-openlabel-v1"
            or meta.get("vocabulary_release") != "cricket-1"
            or meta.get("source_asset") != ref["asset"]
        ):
            raise ValueError("expected the cricket publisher, vocabulary and native source asset")
        if (meta.get("vocabulary_release") != ref["vocabulary_release"]
                or meta.get("source_asset", ref["asset"]) != ref["asset"]):
            raise ValueError("scene vocabulary release or asset mismatch")
        if ref["uid"] not in data.get(ref["collection"], {}):
            raise ValueError("referenced occurrence missing from its typed scene collection")
        # A retry of the same reference contributes at most once per producer/run.
        identity = (ref["workload"], ref["run_id"], key, ref["collection"], ref["uid"])
        if identity not in seen:
            seen.add(identity)
            counts[ref["workload"]] += 1
    return {"schema_version": FORMAT, "referenced_occurrence_revisions": dict(sorted(counts.items())),
            "distinct_scene_revisions_referenced": len({identity[2] for identity in seen})}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--references", type=Path, required=True, help="private workload reference JSONL")
    parser.add_argument("--readback", type=Path, required=True, help="independent openlabel_album_scene JSONL")
    parser.add_argument("--openlabel-schema", type=Path, required=True, help="locally pinned ASAM JSON Schema")
    args = parser.parse_args()
    def records(path: Path) -> list:
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    try:
        summary = check(records(args.references), records(args.readback), json.loads(args.openlabel_schema.read_text()))
    except (ValidationError, ValueError, KeyError, OSError) as error:
        parser.exit(1, f"Observation validation failed ({type(error).__name__}).\n")
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
