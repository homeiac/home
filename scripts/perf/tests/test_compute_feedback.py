"""Replay independent workload traces, including refusal, promotion and rollback."""

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from compute_feedback import Controller, choose, replay

POLICY = dict(
    window_seconds=10,
    max_window_seconds=20,
    min_pending=10,
    min_verified=3,
    min_gain=0.05,
    windows=2,
    quality_timeout=20,
    min_quality_cases=4,
    quality_floor=0.75,
    promotion_ttl_seconds=86400,
)


def observation(t, verified, *, extra=0, quality=None, **kwargs):
    s = dict(
        time=t,
        verified=verified,
        extra_verified=extra,
        errors=0,
        pending=100,
        room={"a": 1.2, "b": 2.4},
        safe={"a": True, "b": True},
        quality=quality,
        healthy=True,
    )
    return {**s, **kwargs}


class FeedbackTest(unittest.TestCase):
    def setUp(self):
        self.c = Controller(POLICY)

    def baseline(self):
        self.assertEqual(self.c.step(observation(0, 0))["action"], "hold")
        result = self.c.step(observation(10, 10))
        self.assertEqual((result["action"], result["pool"]), ("qualify", "b"))

    def begin(self):
        self.baseline()
        self.assertEqual(
            self.c.step(observation(12, 12, quality=[4, 4, 4]))["action"], "add"
        )

    def test_qualified_gain_and_replay_for_different_workload(self):
        samples = [
            observation(0, 0),
            observation(10, 10),
            observation(12, 12, quality=[4, 4, 4]),
            observation(22, 25, extra=2),
            observation(32, 38, extra=4),
            observation(35, 40, extra=4, quality=[4, 4, 4]),
            observation(45, 44, extra=5),
        ]
        for s in samples:
            s.update(room={"embedding-worker": 2}, safe={"embedding-worker": True})
        decisions = [self.c.step(s) for s in samples]
        self.assertEqual(
            [r["action"] for r in decisions],
            ["hold", "qualify", "add", "keep", "recheck", "promote", "rollback"],
        )
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "run.jsonl"
            trace.write_text(
                "".join(
                    json.dumps(dict(observation=s, decision=r)) + "\n"
                    for s, r in zip(samples, decisions)
                )
            )
            self.assertEqual(decisions, replay(trace, POLICY))

    def test_headroom_reorders_and_missing_is_ineligible(self):
        for room, expected in [
            ({"a": 3, "b": 1}, "a"),
            ({"a": 0, "b": None}, None),
            ({"a": 1, "b": 1}, "a"),
        ]:
            self.assertEqual(
                choose(observation(1, 0, room=room), POLICY, set()), expected
            )
        self.assertIsNone(choose(observation(1, 0, pending=0), POLICY, set()))

    def test_holdout_fails(self):
        self.baseline()
        self.assertEqual(
            self.c.step(observation(15, 15, quality=[4, 4, 3]))["action"], "rollback"
        )

    def test_no_verified_candidate_contribution(self):
        self.begin()
        self.assertEqual(self.c.step(observation(32, 100))["action"], "rollback")

    def test_reserve_loss_rolls_back(self):
        self.begin()
        self.assertEqual(
            self.c.step(observation(13, 13, safe={}))["action"], "rollback"
        )

    def test_pending_promotion_requires_second_quality_gate(self):
        self.begin()
        self.c.step(observation(22, 30, extra=2))
        self.c.step(observation(32, 50, extra=4))
        self.assertEqual(
            self.c.step(observation(35, 54, extra=4, quality=[4, 4, 2]))["action"],
            "rollback",
        )

    def test_persisted_promotion_requalifies(self):
        self.assertEqual(
            self.c.step(observation(100, 30, resume=["a", 1, 60]))["pool"], "a"
        )
        self.assertEqual(self.c.phase, "quality")


if __name__ == "__main__":
    unittest.main()
