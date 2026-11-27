"""Reactions suggest possible outcomes only after cricket activity is visible."""

import unittest

from cricket.analyze import proposal
from cricket.reactions import outcome, supplement


class ReactionTests(unittest.TestCase):
    def test_reaction_language_and_counterexamples(self) -> None:
        for text, wanted in [
            ("four!", "four"),
            ("That is six!", "six"),
            ("four or six", "boundary_unclear"),
            ("run out", "run_out"),
            ("he's out!", "dismissal"),
            ("bowled him", "dismissal"),
            ("Howzat!", None),
            ("is he out?", None),
            ("go for six", None),
            ("not four", None),
            ("almost a six", None),
            ("great shot", None),
            ("need 6 runs", None),
        ]:
            with self.subTest(text=text):
                self.assertEqual(outcome(text), wanted)

    def test_missing_role_photos_and_mixed_roles_do_not_gain_audio_results(
        self,
    ) -> None:
        self.assertEqual(supplement([], {"kind": "video"}, {}, "a"), [])
        self.assertEqual(supplement([], {"kind": "photo"}, {}, "a"), [])
        items = [{"data": {"role": "batting"}}, {"data": {"role": "bowling"}}]
        self.assertEqual(supplement(items, {"kind": "video"}, {}, "a"), items)

    def test_possible_boundary_retains_batter_assumption_and_timed_evidence(
        self,
    ) -> None:
        asset = {"kind": "video", "duration": 50}
        window = {
            "start": 0,
            "end": 30,
            "audio": {
                "state": "speech",
                "segments": [{"start": 20, "end": 21, "text": "six!"}],
            },
        }
        role = proposal(
            {"role": "batting", "featured_batter": True}, asset, window, "a"
        )
        rows = supplement([role], asset, window, "a")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[-1]["data"]["actor"], "a")
        self.assertEqual(rows[-1]["data"]["outcome"], "six")
        self.assertEqual(rows[-1]["data"]["start"], 6)
        self.assertTrue(rows[-1]["evidence"]["timing_approximate"])
        self.assertEqual(rows[-1]["evidence"]["confidence"], "possible")
        self.assertEqual(supplement(rows, asset, window, "a"), rows)


if __name__ == "__main__":
    unittest.main()
