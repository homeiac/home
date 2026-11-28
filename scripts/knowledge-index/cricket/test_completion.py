"""Versioned negatives use the shared writer and checker without inventing faces."""

import copy
import json
from pathlib import Path
from types import ModuleType
from uuid import UUID

import pytest

# Imported pytest fixtures are intentionally shadowed by injected parameters.
# ruff: noqa: F811
from check_media_observations import check, pg_digest
from cricket.openlabel import publish, scene
from cricket.test_openlabel import inputs, schema, shared  # noqa: F401
from cricket.test_publication_readback import local_pg  # noqa: F401
from cricket.vocabulary import COMPLETION

COMPLETE = {
    "state": "complete",
    "analysis_version": "analysis-v1",
    "analysis_digest": "fixture",
}


def reference(row: dict) -> dict:
    """Reference the completion occurrence, not a fabricated delivery or face."""
    uid = next(
        k
        for k, v in row["scene"]["openlabel"]["contexts"].items()
        if v["type"] == COMPLETION
    )
    return {
        **{k: row[k] for k in ("album", "asset", "revision", "digest")},
        "contract_version": 1,
        "workload": "cricket-indexer",
        "run_id": "fixture",
        "vocabulary_release": "cricket-2",
        "collection": "contexts",
        "uid": uid,
        "evidence_ref": "private/fixture",
    }


def test_no_event_commits_reads_back_and_deduplicates(
    local_pg: object, shared: ModuleType, schema: Path, inputs: tuple
) -> None:
    asset, registry, _ = inputs
    registry["frames"][0]["faces"] = []
    doc = scene(shared, asset, registry, [], completion=COMPLETE)
    album = str(UUID(int=3))
    for _ in range(2):
        publish(local_pg, shared, album, {asset["id"]: doc}, schema)
    rows = [
        {"album": album, "asset": asset["id"], "revision": r, "digest": d, "scene": s}
        for r, d, s in local_pg.execute(
            "SELECT revision,digest,scene FROM openlabel_album_scene WHERE album=%s AND asset=%s",
            (album, asset["id"]),
        )
    ]
    assert len(rows) == 1
    data = rows[0]["scene"]["openlabel"]
    assert not data["actions"] and not data["events"] and not data["objects"]
    result = check([reference(rows[0])], rows, json.loads(schema.read_text()))
    assert result["referenced_occurrence_revisions"] == {"cricket-indexer": 1}


@pytest.mark.parametrize("mutation", ["pending", "no_frames", "flag", "analysis"])
def test_pending_cannot_be_published_as_completed(
    shared: ModuleType, inputs: tuple, mutation: str
) -> None:
    asset, registry, _ = inputs
    completion = dict(COMPLETE)
    if mutation == "pending":
        registry["frames"][0]["state"] = "pending"
    elif mutation == "no_frames":
        registry["frames"] = []
    elif mutation == "flag":
        registry["detection_complete"] = False
    else:
        completion["state"] = "running"
    with pytest.raises(ValueError, match="completed analysis"):
        scene(shared, asset, registry, [], completion=completion)


@pytest.mark.parametrize(
    "mutation", ["missing", "pending", "duplicate", "result", "fingerprint", "version"]
)
def test_checker_independently_rejects_false_completion(
    shared: ModuleType, schema: Path, inputs: tuple, mutation: str
) -> None:
    asset, registry, events = inputs
    doc = scene(shared, asset, registry, events, completion=COMPLETE)
    row = {
        "album": str(UUID(int=3)),
        "asset": asset["id"],
        "revision": 1,
        "digest": pg_digest(doc),
        "scene": doc,
    }
    ref = reference(row)
    data = doc["openlabel"]
    values = data["contexts"][ref["uid"]]["context_data"]["text"]
    if mutation == "missing":
        del data["contexts"][ref["uid"]]
    elif mutation == "pending":
        data["frames"]["0"]["frame_properties"]["detection_state"] = "pending"
    elif mutation == "duplicate":
        values.append(copy.deepcopy(values[0]))
    else:
        field = {
            "result": "result",
            "fingerprint": "source_fingerprint",
            "version": "analysis_version",
        }[mutation]
        next(v for v in values if v["name"] == field)["val"] = (
            "no_event" if mutation == "result" else ""
        )
    row["digest"] = ref["digest"] = pg_digest(doc)
    with pytest.raises(ValueError, match="completion"):
        check([ref], [row], json.loads(schema.read_text()))
