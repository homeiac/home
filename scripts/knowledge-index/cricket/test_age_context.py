"""Recording-date age is a clue, and cannot override identity corrections or ambiguity."""

import datetime as dt
import unittest

from cricket.age_context import age_context, attach
from cricket.analyze import proposal
from cricket.context import apply_hint


class AgeContextTests(unittest.TestCase):
    def test_dates_and_cache_identity(self) -> None:
        asset = {
            "exifInfo": {"dateTimeOriginal": "2021-09-25T20:39:18Z"},
            "fileCreatedAt": "2021-09-25T20:39:18Z",
        }
        context = age_context(asset, "2010-05-28", today=dt.date(2026, 1, 1))
        self.assertEqual((context["age_years"], context["age_months"]), (11, 3))
        prepared = {"cache_key": "original", "windows": [{}]}
        attach(prepared, context)
        key = prepared["cache_key"]
        attach(prepared, context)
        self.assertEqual(key, prepared["cache_key"])
        attach(prepared, {**context, "age_years": 12})
        self.assertNotEqual(key, prepared["cache_key"])
        self.assertEqual(age_context(asset, None)["status"], "unavailable")
        self.assertEqual(age_context(asset, "2022-01-01")["status"], "invalid_dates")
        self.assertEqual(
            age_context({**asset, "fileCreatedAt": "2023-01-01"}, "2010-05-28")[
                "status"
            ],
            "conflicting_dates",
        )
        self.assertEqual(
            age_context({"fileCreatedAt": "2021-05-27"}, "2010-05-28")["age_years"], 10
        )

    def test_age_conflict_blocks_portrait_and_batting_assumptions_including_caption_fallback(
        self,
    ) -> None:
        asset = {"kind": "video", "duration": 30}
        window = {
            "start": 0,
            "end": 30,
            "audio": {"state": "no_audio", "segments": []},
            "identity_context": {"status": "known", "age_years": 11, "age_months": 3},
        }
        raw = {
            "role": "batting",
            "actor": "adil",
            "featured_batter": True,
            "age_compatibility": "incompatible",
        }
        result = proposal(raw, asset, window, "a", reference=True)
        self.assertIsNone(result["data"]["actor"])
        self.assertEqual(result["evidence"]["identity_basis"], "age_conflict")
        result = apply_hint(result, "A cricket batter holding a bat.", "a")
        self.assertIsNone(result["data"]["actor"])
        unknown = proposal({**raw, "age_compatibility": "unclear"}, asset, window, "a")
        self.assertEqual(unknown["data"]["actor"], "a")
        bowler = proposal(
            {**raw, "role": "bowling", "age_compatibility": "compatible"},
            asset,
            window,
            "a",
        )
        self.assertIsNone(bowler["data"]["actor"])
        other = proposal(
            {**raw, "actor": "other", "age_compatibility": "compatible"},
            asset,
            window,
            "a",
        )
        self.assertIsNone(apply_hint(other, "A cricket batter.", "a")["data"]["actor"])


if __name__ == "__main__":
    unittest.main()
