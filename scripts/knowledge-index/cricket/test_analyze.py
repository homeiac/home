"""Best-effort proposals retain uncertain results and protect temporal/identity boundaries."""

import unittest

from cricket.analyze import parse_reply, prompt, proposal
from cricket.models import request_body


class AnalyzeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.asset = {"kind": "video", "duration": 120}
        self.window = {
            "start": 20,
            "end": 50,
            "positions": [21, 25, 30, 35, 40, 45, 48, 49],
            "audio": {
                "state": "speech",
                "segments": [{"start": 42, "end": 43, "text": "six!"}],
            },
        }

    def test_pre_roll_and_aftermath(self) -> None:
        raw = {
            "role": "batting",
            "featured_batter": True,
            "outcome": "six",
            "runup_start": 30,
            "outcome_end": 43,
        }
        result = proposal(raw, self.asset, self.window, "a")
        self.assertEqual((result["data"]["start"], result["data"]["end"]), (20, 48))
        self.assertEqual(result["data"]["actor"], "a")
        self.assertEqual(result["evidence"]["identity_basis"], "user_album_rule")
        result = proposal(
            {**raw, "runup_start": None, "release": 30}, self.asset, self.window, "a"
        )
        self.assertEqual(result["data"]["start"], 15)
        self.assertTrue(result["evidence"]["timing_approximate"])
        result = proposal(
            {"role": "batting", "runup_start": 2, "outcome_end": 7},
            {"kind": "video", "duration": 8},
            {**self.window, "start": 0, "end": 8},
            "a",
        )
        self.assertEqual((result["data"]["start"], result["data"]["end"]), (0, 8))

    def test_bowling_identity_and_runout_are_separate(self) -> None:
        raw = {
            "role": "bowling",
            "actor": "adil",
            "outcome": "run_out",
            "wicket_credit": "bowler",
        }
        result = proposal(raw, self.asset, self.window, "a")
        self.assertIsNone(result["data"]["actor"])
        self.assertEqual(result["data"]["wicket_credit"], "run_out")
        result = proposal(raw, self.asset, self.window, "a", reference=True)
        self.assertEqual(result["data"]["actor"], "a")
        wicket = proposal(
            {**raw, "outcome": "dismissal"},
            self.asset,
            self.window,
            "a",
            reference=True,
        )
        self.assertEqual(wicket["data"]["wicket_credit"], "bowler")
        partner = proposal(
            {
                "role": "batting",
                "actor": "other",
                "featured_batter": True,
                "outcome": "dismissal",
            },
            self.asset,
            self.window,
            "a",
        )
        self.assertIsNone(partner["data"]["actor"])

    def test_uncertain_events_are_kept_and_photo_has_no_result(self) -> None:
        result = proposal(
            {"role": "batting", "outcome": "boundary_unclear", "confidence": "low"},
            self.asset,
            self.window,
            "a",
        )
        self.assertEqual(result["data"]["outcome"], "boundary_unclear")
        self.assertEqual(result["evidence"]["confidence"], "possible")
        result = proposal(
            {"role": "batting", "outcome": "six", "runup_start": 999},
            {"kind": "photo", "duration": None},
            self.window,
            "a",
        )
        self.assertIsNone(result["data"]["start"])
        self.assertEqual(result["data"]["outcome"], "unknown")

    def test_invalid_or_out_of_window_observations_are_rejected(self) -> None:
        for raw in (
            {"role": "golf"},
            {"outcome": "seven"},
            {"runup_start": 10},
            {"release": float("nan")},
            {"runup_start": 40, "outcome_end": 30},
        ):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                proposal(raw, self.asset, self.window, "a")
        for reply in (
            "none",
            "{}",
            '{"events":{}}',
            '{"events":[' + ",".join(["{}"] * 13) + "]}",
        ):
            with self.assertRaises(ValueError):
                parse_reply(reply)
        self.assertEqual(len(parse_reply('```json\n{"events":[{},{}]}\n```')), 2)
        self.assertIn("FIRST image", prompt(self.window, reference=True))
        self.assertIn("PHOTO", prompt(self.window, photo=True))

    def test_model_requests_preserve_image_order_and_disable_reasoning(self) -> None:
        route, body = request_body(
            {"api": "ollama", "model": "fixture"}, "prompt", ["first", "second"]
        )
        self.assertEqual(route, "/api/chat")
        self.assertFalse(body["think"])
        self.assertEqual(body["messages"][0]["images"], ["first", "second"])
        route, body = request_body(
            {"api": "openai", "model": "fixture"}, "prompt", ["first"]
        )
        self.assertEqual(route, "/v1/chat/completions")
        self.assertEqual(
            body["messages"][0]["content"][1]["image_url"]["url"],
            "data:image/jpeg;base64,first",
        )


if __name__ == "__main__":
    unittest.main()
