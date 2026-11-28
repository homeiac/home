"""Native face IDs survive unnamed results, retries, and changing recognition."""

import base64
import io
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from cricket.analyze import proposal
from cricket.face_context import for_window, load, normalize, subject
from cricket.immich_frames import frame_bytes, synchronize

OWNER = "10000000-0000-4000-8000-000000000001"
ASSET = "10000000-0000-4000-8000-000000000002"
FRAME = "10000000-0000-4000-8000-000000000003"
FACE = "10000000-0000-4000-8000-000000000004"
OTHER = "10000000-0000-4000-8000-000000000005"


def native(face_id=FACE, person=None):
    return {
        "id": face_id,
        "person": person,
        "imageWidth": 100,
        "imageHeight": 100,
        "boundingBoxX1": 20,
        "boundingBoxY1": 20,
        "boundingBoxX2": 30,
        "boundingBoxY2": 35,
    }


def jpeg():
    out = io.BytesIO()
    Image.new("RGB", (100, 100), "blue").save(out, "JPEG")
    return base64.b64encode(out.getvalue()).decode()


def test_each_unnamed_face_has_distinct_native_id():
    faces = normalize([native(), native(OTHER)])
    assert [f["face_id"] for f in faces] == [FACE, OTHER]
    assert all(f["person_id"] is None and f["name"] is None for f in faces)
    for invalid in ([native(), native()], [native("unknown")]):
        with pytest.raises(ValueError):
            normalize(invalid)


def test_frame_identity_is_retry_stable_and_does_not_change_pixels():
    image = jpeg()
    encoded = frame_bytes(image, "key")
    assert encoded == frame_bytes(image, "key")
    assert encoded != frame_bytes(image, "different timestamp")
    with (
        Image.open(io.BytesIO(base64.b64decode(image))) as before,
        Image.open(io.BytesIO(base64.b64decode(encoded))) as after,
    ):
        assert before.tobytes() == after.tobytes()


def test_pending_empty_is_not_complete_and_retry_reuses_native_asset():
    asset = {"id": ASSET, "owner": OWNER, "fingerprint": "same", "kind": "video"}
    prepared = {"windows": [{"positions": [2], "frames": [jpeg()]}]}
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        with (
            patch(
                "cricket.immich_frames.request",
                return_value={"frame_asset": FRAME, "faces": []},
            ) as request,
            patch("cricket.immich_frames.completed", return_value=set()),
        ):
            result = synchronize(asset, prepared, folder)
            assert not result["complete"] and result["pending"] == 1
            assert request.call_args.args[0]["image"]
        with (
            patch(
                "cricket.immich_frames.request",
                return_value={"frame_asset": FRAME, "faces": [native()]},
            ) as request,
            patch("cricket.immich_frames.completed", return_value={FRAME}),
        ):
            result = synchronize(asset, prepared, folder)
            assert result["complete"] and result["faces"] == 1
            assert all("image" not in call.args[0] for call in request.call_args_list)
        value = load(folder, asset)
        assert value["frames"][0]["faces"][0]["face_id"] == FACE
        assert for_window(value, {"positions": [2]})[0]["frame_index"] == 0
        assert for_window(value, {"positions": [3]}) == []
        with pytest.raises(ValueError):
            load(folder, {**asset, "owner": OTHER})
        with pytest.raises(ValueError):
            synchronize({**asset, "fingerprint": "changed"}, prepared, folder)


def test_native_person_overrides_batting_assumption_without_changing_face_id():
    faces = [
        {
            "timestamp": 2,
            "frame_asset": FRAME,
            "faces": normalize([native(person={"id": OTHER, "name": ""})]),
        }
    ]
    where = {"timestamp": 2, "person_box": [0.1, 0.1, 0.5, 0.8], "face_box": None}
    assert subject(where, faces)["face_id"] == FACE
    assert subject({**where, "timestamp": 3}, faces) is None
    ambiguous = json.loads(json.dumps(faces))
    ambiguous[0]["faces"].append(normalize([native(ASSET)])[0])
    assert subject(where, ambiguous) is None
    window = {
        "start": 0,
        "end": 10,
        "positions": [2],
        "audio": {"state": "no_audio", "segments": []},
        "immich_faces": faces,
    }
    raw = {
        "role": "batting",
        "actor": "adil",
        "featured_batter": True,
        "subject_location": {"frame_index": 0, "person_box": where["person_box"]},
    }
    result = proposal(
        raw, {"kind": "video", "duration": 20}, window, OWNER, reference=True
    )
    assert result["data"]["actor"] == OTHER
    assert result["evidence"]["subject_face"]["face_id"] == FACE
    assert result["evidence"]["identity_basis"] == "immich_face_match"
