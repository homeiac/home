"""Three producers share a scene revision. All identifiers and observations are synthetic."""
import json
import os
from pathlib import Path

import pytest
from jsonschema import Draft7Validator, FormatChecker, ValidationError

from check_media_observations import REFERENCE, check, pg_digest


def batch():
    album, asset = "00000000-0000-4000-8000-000000000001", "00000000-0000-4000-8000-000000000002"
    scene = {"openlabel": {"metadata": {"schema_version": "1.0.0", "vocabulary_release": "cricket-1", "producer": "cricket-openlabel-v1", "source_asset": asset},
             "objects": {"0": {"name": "Dog occurrence", "type": "dog"}},
             "actions": {"1": {"name": "Batting", "type": "batting"}},
             "contexts": {"2": {"name": "Scene", "type": "scene_description"}},
             "relations": {"3": {"name": "present during", "type": "present_during",
                                "rdf_subjects": [{"type": "object", "uid": "0"}],
                                "rdf_objects": [{"type": "action", "uid": "1"}]}}}}
    row = dict(album=album, asset=asset, revision=1, digest=pg_digest(scene), scene=scene)
    refs = []
    for workload, collection, uid in [("immich-pet-tagger", "objects", "0"), ("cricket-indexer", "actions", "1"),
                                      ("knowledge-index", "contexts", "2")]:
        refs.append(dict(contract_version=1, workload=workload, run_id="fixture", album=album, asset=asset,
                         revision=1, digest=row["digest"], vocabulary_release="cricket-1",
                         collection=collection, uid=uid, evidence_ref="private-fixture/" + uid))
    return refs, row


def test_machine_readable_reference_contract():
    refs, _ = batch()
    validator = Draft7Validator(json.loads(REFERENCE.read_text()), format_checker=FormatChecker())
    for ref in refs:
        validator.validate(ref)
    with pytest.raises(ValidationError):
        validator.validate({**refs[0], "asset": "wrong-id"})


@pytest.fixture
def definition():
    schema = os.environ.get("ASAM_OPENLABEL_1_0_SCHEMA")
    if not schema:
        pytest.skip("set ASAM_OPENLABEL_1_0_SCHEMA to the pinned official schema for integration tests")
    return json.loads(Path(schema).read_text())


def test_readback_cross_workload_dedup_and_revisions(definition):
    refs, row = batch()
    summary = check(refs + refs, [row], definition)
    assert summary["distinct_scene_revisions_referenced"] == 1
    assert summary["referenced_occurrence_revisions"] == {ref["workload"]: 1 for ref in refs}
    corrected = json.loads(json.dumps(row))
    corrected["revision"] = 2
    corrected["scene"]["openlabel"]["objects"]["0"]["name"] = "Reviewed dog occurrence"
    corrected["digest"] = pg_digest(corrected["scene"])
    later = {**refs[0], "revision": 2, "digest": corrected["digest"]}
    assert check(refs + [later], [row, corrected], definition)["distinct_scene_revisions_referenced"] == 2


@pytest.mark.parametrize("field,value", [("revision", 2), ("uid", "9"), ("digest", "0"*64),
                                        ("vocabulary_release", "wrong")])
def test_invalid_reference_is_rejected(definition, field, value):
    refs, row = batch()
    with pytest.raises(ValueError):
        check([{**refs[0], field: value}], [row], definition)


def test_dangling_typed_edge_is_rejected_even_with_valid_digest(definition):
    refs, row = batch()
    row["scene"]["openlabel"]["relations"]["3"]["rdf_objects"][0]["uid"] = "404"
    row["digest"] = pg_digest(row["scene"])
    refs[0]["digest"] = row["digest"]
    with pytest.raises(ValueError, match="missing typed occurrence"):
        check(refs[:1], [row], definition)

def test_cricket_cannot_claim_another_publishers_revision(definition):
    refs, row = batch()
    row["scene"]["openlabel"]["metadata"]["producer"] = "another-publisher"
    row["digest"] = pg_digest(row["scene"])
    cricket = next(ref for ref in refs if ref["workload"] == "cricket-indexer")
    with pytest.raises(ValueError, match="cricket publisher"):
        check([{**cricket, "digest": row["digest"]}], [row], definition)
