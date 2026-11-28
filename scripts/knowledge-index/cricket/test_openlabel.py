"""Exercise cricket scenes with the actual life-stage binder and pinned v1 schema."""

import copy
import json
import os
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from cricket.immich_frames import frame_key
from cricket.ledger import OUTCOMES as LEDGER_OUTCOMES
from cricket.ledger import ROLES
from cricket.openlabel import (
    PRODUCER,
    publish,
    registry_for_scene,
    scene,
    shared_module,
)
from cricket.test_faces import ASSET, FACE, FRAME, OTHER, OWNER, jpeg
from cricket.vocabulary import ACTIONS, OUTCOMES


@pytest.fixture
def shared() -> ModuleType:
    """Require the real shared implementation for integration checks, without copying it."""
    path = os.environ.get("CRICKET_OPENLABEL_SHARED_MODULE")
    if not path:
        pytest.skip("Set CRICKET_OPENLABEL_SHARED_MODULE for life-stage integration")
    return shared_module(Path(path))


@pytest.fixture
def schema() -> Path:
    """Use the same pinned OpenLABEL 1.0.0 schema as the publication command."""
    path = os.environ.get("CRICKET_OPENLABEL_SCHEMA")
    if not path:
        pytest.skip("Set CRICKET_OPENLABEL_SCHEMA for schema validation")
    return Path(path)


@pytest.fixture
def inputs() -> tuple[dict, dict, list[dict]]:
    """An unnamed player, a separate unnamed bystander, and a corrected attempt."""
    asset = {"owner": OWNER, "id": ASSET, "fingerprint": "original-v1"}
    registry = {
        "owner": OWNER,
        "asset": ASSET,
        "fingerprint": "original-v1",
        "detection_complete": True,
        "frames": [
            {
                "timestamp": 12.5,
                "frame_asset": FRAME,
                "state": "detected",
                "image_width": 1000,
                "image_height": 500,
                "faces": [
                    {
                        "face_id": FACE,
                        "person_id": None,
                        "face_box": [0.2, 0.1, 0.1, 0.2],
                    },
                    {
                        "face_id": OTHER,
                        "person_id": None,
                        "face_box": [0.7, 0.1, 0.1, 0.2],
                    },
                ],
            }
        ],
    }
    events = [
        {
            "owner": OWNER,
            "asset": ASSET,
            "fingerprint": "original-v1",
            "id": "delivery-1",
            "revision": 2,
            "dismissed": False,
            "review_state": "corrected",
            "overrides": {"outcome": "attempted_run_out"},
            "data": {
                "actor": None,
                "role": "batting",
                "outcome": "attempted_run_out",
                "wicket_credit": "unknown",
                "start": 2.5,
                "end": 25,
                "delivery_start": 12.5,
                "outcome_end": 23,
            },
            "evidence": {
                "identity_basis": "unresolved",
                "subject_location": {
                    "timestamp": 12.5,
                    "person_box": [0.1, 0, 0.3, 0.9],
                    "face_box": None,
                },
            },
        }
    ]
    return asset, registry, events


def test_vocabulary_covers_saved_states_with_distinct_permanent_codes() -> None:
    assert set(ACTIONS) == ROLES
    assert set(OUTCOMES) == LEDGER_OUTCOMES
    terms = [*ACTIONS.values(), *OUTCOMES.values()]
    assert len({code for code, _ in terms}) == len(terms)
    assert all(definition for _, definition in terms)


def test_legacy_dimensions_require_matching_image_without_mutating_checkpoint(
    tmp_path: Path, inputs: tuple[dict, dict, list[dict]]
) -> None:
    asset, registry, _ = inputs
    image = jpeg()
    frame = registry["frames"][0]
    frame.pop("image_width")
    frame.pop("image_height")
    frame["key"] = frame_key(asset, 12.5, image)
    (tmp_path / "faces").mkdir()
    checkpoint = tmp_path / "faces" / (ASSET + ".json")
    checkpoint.write_text(json.dumps(registry))
    (tmp_path / (ASSET + ".json")).write_text(
        json.dumps({"windows": [{"positions": [12.5], "frames": [image]}]})
    )
    assert registry_for_scene(tmp_path, asset)["frames"][0]["image_width"] == 100
    assert json.loads(checkpoint.read_text()) == registry
    frame["key"] = "changed"
    checkpoint.write_text(json.dumps(registry))
    with pytest.raises(ValueError, match="exact uploaded"):
        registry_for_scene(tmp_path, asset)


def test_all_unnamed_faces_geometry_times_and_corrected_outcome(
    shared: ModuleType, schema: Path, inputs: tuple[dict, dict, list[dict]]
) -> None:
    asset, registry, events = inputs
    result = scene(shared, asset, registry, events)
    shared.validate_scenes({ASSET: result}, schema)
    data = result["openlabel"]
    faces = {
        shared.fields(o["object_data"])["face_id"] for o in data["objects"].values()
    }
    assert faces == {FACE, OTHER}
    uid = shared.stable_id(ASSET, "immich", FACE)
    frame = data["frames"]["0"]
    assert frame["frame_properties"]["timestamp"] == 12.5
    assert frame["objects"][uid]["object_data"]["bbox"][0]["val"] == pytest.approx(
        [250, 100, 100, 100]
    )
    action = next(iter(data["actions"].values()))
    assert shared.fields(action["action_data"])["review_state"] == "corrected"
    assert {n["name"]: n["val"] for n in action["action_data"]["num"]}[
        "start_seconds"
    ] == 2.5
    assert (
        next(iter(data["events"].values()))["type"] == OUTCOMES["attempted_run_out"][0]
    )
    actors = [r for r in data["relations"].values() if r["type"] == "actor"]
    assert actors[0]["rdf_objects"] == [{"type": "object", "uid": uid}]
    bystander = data["objects"][shared.stable_id(ASSET, "immich", OTHER)]
    assert "action_withheld" in shared.fields(bystander["object_data"])


@pytest.mark.parametrize("reason", ["no_box", "ambiguous", "changed_person"])
def test_batting_assumption_never_forces_an_unsupported_face_binding(
    shared: ModuleType, schema: Path, inputs: tuple[dict, dict, list[dict]], reason: str
) -> None:
    asset, registry, events = inputs
    events[0]["data"]["actor"] = OWNER
    events[0]["evidence"]["identity_basis"] = "user_album_rule"
    if reason == "no_box":
        events[0]["evidence"].pop("subject_location")
    elif reason == "ambiguous":
        events[0]["evidence"]["subject_location"]["person_box"] = [0, 0, 1, 1]
    else:
        registry["frames"][0]["faces"][0]["person_id"] = OTHER
    result = scene(shared, asset, registry, events)
    shared.validate_scenes({ASSET: result}, schema)
    data = result["openlabel"]
    assert all(r["type"] != "actor" for r in data["relations"].values())
    assert all(
        "action_withheld" in shared.fields(o["object_data"])
        for o in data["objects"].values()
    )
    assert (
        shared.fields(next(iter(data["actions"].values()))["action_data"])["person_id"]
        == OWNER
    )


def test_correction_retains_occurrences_and_dismissal_removes_action_not_faces(
    shared: ModuleType, schema: Path, inputs: tuple[dict, dict, list[dict]]
) -> None:
    asset, registry, events = inputs
    before = scene(shared, asset, registry, events)
    events[0]["revision"] += 1
    events[0]["data"]["outcome"] = "four"
    changed = scene(shared, asset, registry, events)
    for kind in ("objects", "actions", "events"):
        assert before["openlabel"][kind].keys() == changed["openlabel"][kind].keys()
    events[0]["dismissed"] = True
    dismissed = scene(shared, asset, registry, events)
    shared.validate_scenes({ASSET: dismissed}, schema)
    assert (
        not dismissed["openlabel"]["actions"] and not dismissed["openlabel"]["events"]
    )
    assert len(dismissed["openlabel"]["objects"]) == 2


def test_scope_changes_and_duplicate_native_instances_are_rejected(
    shared: ModuleType, inputs: tuple[dict, dict, list[dict]]
) -> None:
    asset, registry, events = inputs
    for field in ("owner", "asset", "fingerprint"):
        changed = copy.deepcopy(registry)
        changed[field] = "different"
        with pytest.raises(ValueError, match="scope"):
            scene(shared, asset, changed, events)
    registry["frames"].append(copy.deepcopy(registry["frames"][0]))
    with pytest.raises(ValueError, match="repeated"):
        scene(shared, asset, registry, events)


def test_publication_validates_and_preserves_other_producers(
    shared: ModuleType,
    schema: Path,
    inputs: tuple[dict, dict, list[dict]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset, registry, events = inputs
    scenes = {ASSET: scene(shared, asset, registry, events)}
    conn = MagicMock()
    conn.execute.return_value.fetchone.side_effect = [
        ("openlabel_album_scene",),
        ({"openlabel": {"metadata": {"producer": "life-stage"}}},),
    ]
    writer = MagicMock(return_value=scenes)
    monkeypatch.setattr(shared, "persist", writer)
    with pytest.raises(ValueError, match="another producer"):
        publish(conn, shared, OWNER, scenes, schema)
    writer.assert_not_called()
    conn.execute.return_value.fetchone.side_effect = [
        ("openlabel_album_scene",),
        ({"openlabel": {"metadata": {"producer": PRODUCER}}},),
    ]
    assert publish(conn, shared, OWNER, scenes, schema) == scenes
    writer.assert_called_once_with(conn, OWNER, scenes)
