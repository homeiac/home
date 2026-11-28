"""Check that repeat count, attribution and frame identity survive paired scoring."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from review_pass_trial import compare


class PassTrialTests(unittest.TestCase):
    def test_counterbalanced_review_counts_and_mismatched_inputs(self):
        with TemporaryDirectory() as tmp:
            paths = [Path(tmp) / name for name in ("first", "mirror")]
            for folder in paths:
                folder.mkdir()
                (folder / "sample.json").write_text(json.dumps([[{}, "teen", []]]))
                for backend in ("mac-metal", "rtx3070"):
                    for mode in ("baseline", "candidate"):
                        times = (
                            {"joint_seconds": 1}
                            if mode == "candidate"
                            else {"age_seconds": 1, "action_seconds": 1}
                        )
                        row = dict(
                            index=0,
                            state="complete",
                            outcome={"stage": "teen", "action": "stands"},
                            frame_hashes=["full", "crop"],
                            raw_joint={"stage": "teen", "confidence": "high"},
                            **times,
                        )
                        for repeat in (1, 2):
                            (folder / f"{backend}-{mode}-{repeat}.json").write_text(
                                json.dumps(
                                    dict(results=[row], slots=3, rate=3, seconds=20)
                                )
                            )
            options = compare(paths[0], mirror=paths[1])
            self.assertEqual(options, {0: [{"key": "0-0", "action": "stands"}]})
            before = compare(paths[0], {"0-0": True}, paths[1])["mac-metal/baseline"]
            self.assertEqual(
                (before["inference_calls"], before["both_correct"], before["per_min"]),
                (8, 4, 3),
            )
            self.assertEqual(before["reviewed_stage_exact"], 4)
            after = compare(paths[0], {"0-0": False}, paths[1])["mac-metal/candidate"]
            self.assertEqual((after["inference_calls"], after["both_correct"]), (4, 0))
            with self.assertRaisesRegex(ValueError, "rating"):
                compare(paths[0], {}, paths[1])
            last = paths[1] / "rtx3070-candidate-2.json"
            last.write_text(last.read_text().replace('"crop"', '"other"'))
            with self.assertRaisesRegex(ValueError, "inputs differed"):
                compare(paths[0], mirror=paths[1])
