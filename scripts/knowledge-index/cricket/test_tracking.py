"""Tracking reuses sampled coordinates without jumping across cuts, sources or identity conflicts."""

import base64
import io
import unittest

from PIL import Image

from cricket.analyze import proposal
from cricket.tracking import advance, box, location, with_anchor


class TrackingTests(unittest.TestCase):
    def setUp(self) -> None:
        output = io.BytesIO()
        Image.new("RGB", (100, 80), "red").save(output, "JPEG")
        self.frame = base64.b64encode(output.getvalue()).decode()
        self.asset = {
            "id": "v",
            "fingerprint": "same",
            "kind": "video",
            "duration": 120,
        }
        self.window = {
            "start": 0,
            "end": 30,
            "positions": [10, 25],
            "frames": [self.frame] * 2,
            "audio": {"state": "no_audio", "segments": []},
            "identity_context": {"status": "known", "age_years": 11},
        }
        self.raw = {
            "role": "bowling",
            "actor": "adil",
            "age_compatibility": "compatible",
            "subject_location": {
                "frame_index": 1,
                "person_box": [0.2, 0.1, 0.3, 0.8],
                "face_box": [0.25, 0.12, 0.1, 0.15],
            },
        }

    def test_coordinate_validation_and_source_fencing(self) -> None:
        for invalid in (
            [0, 0, 2, 1],
            [0, 0, True, 1],
            [-0.1, 0, 0.2, 0.2],
            [0, 0, 0, 0.1],
            None,
        ):
            self.assertIsNone(box(invalid))
        self.assertEqual(location(self.raw, self.window)["timestamp"], 25)
        self.assertIsNone(
            location(
                {
                    **self.raw,
                    "subject_location": {"frame_index": 5, "face_box": [0, 0, 1, 1]},
                },
                self.window,
            )
        )
        p = proposal(self.raw, self.asset, self.window, "a", reference=True)
        anchor = advance([p], self.asset, self.window, "a")
        self.assertIsNotNone(anchor)
        self.assertNotIn(
            "track_anchor",
            with_anchor(self.window, anchor, {**self.asset, "id": "other"}),
        )
        self.assertNotIn(
            "track_anchor",
            with_anchor({**self.window, "start": 90, "end": 120}, anchor, self.asset),
        )
        self.assertIsNone(advance([], self.asset, self.window, "a"))

    def test_same_player_continues_but_cuts_age_conflicts_and_assumptions_do_not_identify_bowlers(
        self,
    ) -> None:
        p = proposal(self.raw, self.asset, self.window, "a", reference=True)
        anchor = advance([p], self.asset, self.window, "a")
        later = with_anchor(
            {**self.window, "start": 20, "end": 50, "positions": [30, 45]},
            anchor,
            self.asset,
        )
        raw = {
            **self.raw,
            "actor": "unknown",
            "track_match": True,
            "scene_continuity": "same_scene",
        }
        tracked = proposal(raw, self.asset, later, "a")
        self.assertEqual(tracked["data"]["actor"], "a")
        self.assertEqual(
            tracked["evidence"]["identity_basis"], "video_track_suggestion"
        )
        for patch in (
            {"scene_continuity": "cut"},
            {"scene_continuity": "unclear"},
            {"age_compatibility": "incompatible"},
            {"subject_location": None},
        ):
            self.assertIsNone(
                proposal({**raw, **patch}, self.asset, later, "a")["data"]["actor"]
            )
        later["track_anchor"]["basis"] = "user_album_rule"
        self.assertIsNone(proposal(raw, self.asset, later, "a")["data"]["actor"])


if __name__ == "__main__":
    unittest.main()
