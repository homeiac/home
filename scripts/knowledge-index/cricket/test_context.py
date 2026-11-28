"""Weak role suggestions can reuse captions without asserting bowler identity or results."""

import base64
import io
import unittest

from PIL import Image

from cricket.analyze import proposal
from cricket.contact_sheet import sheet
from cricket.context import apply_hint, role_hint


class ContextTests(unittest.TestCase):
    def test_caption_hints_and_identity_provenance(self) -> None:
        self.assertEqual(
            role_hint(
                "The main subject is a young batter in a blue uniform playing cricket."
            ),
            "batting",
        )
        self.assertEqual(
            role_hint("The batter waits while the bowler delivers a ball."), None
        )
        self.assertEqual(role_hint("The bowler runs to the wicket."), "bowling")
        self.assertIsNone(role_hint("People visiting a temple."))
        asset = {"kind": "video", "duration": 30}
        window = {
            "start": 0,
            "end": 30,
            "audio": {"state": "no_speech", "segments": []},
        }
        value = proposal(
            {"role": "bowling", "confidence": "unclear"}, asset, window, "a"
        )
        improved = apply_hint(
            value, "A cricket batter in a helmet stands at the crease.", "a"
        )
        self.assertEqual(improved["data"]["role"], "batting")
        self.assertEqual(improved["data"]["actor"], "a")
        self.assertEqual(improved["data"]["outcome"], "unknown")
        self.assertIsNone(improved["data"]["delivery_start"])
        self.assertEqual(improved["evidence"]["identity_basis"], "user_album_rule")
        anchored = proposal(
            {"role": "bowling", "release": 12, "outcome": "dismissal"},
            asset,
            window,
            "a",
        )
        self.assertEqual(
            apply_hint(anchored, "A cricket batter in a helmet.", "a"), anchored
        )

    def test_contact_sheet_contains_all_frames_and_bounds_work(self) -> None:
        output = io.BytesIO()
        Image.new("RGB", (100, 80), "red").save(output, "JPEG")
        frame = base64.b64encode(output.getvalue()).decode()
        self.assertEqual(sheet({"frames": [frame], "positions": [0]}), frame)
        combined = Image.open(
            io.BytesIO(
                base64.b64decode(
                    sheet({"frames": [frame] * 8, "positions": list(range(8))})
                )
            )
        )
        self.assertEqual(combined.size, (1536, 568))
        with self.assertRaises(ValueError):
            sheet({"frames": []})


if __name__ == "__main__":
    unittest.main()
