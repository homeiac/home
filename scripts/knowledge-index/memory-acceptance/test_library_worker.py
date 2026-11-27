"""Check malformed responses, two-pass resumption and native action attribution."""

import unittest
from unittest.mock import patch

import library_worker as worker


class LibraryWorkerTests(unittest.TestCase):
    def test_model_must_return_an_object(self):
        for raw in ("[]", "null", None, '""'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                worker.decode(raw)

    @patch.object(worker, "frames", return_value=[b"marked", b"crop"])
    @patch.object(
        worker, "observe", return_value={"verb": "stands", "action": "with folded arms"}
    )
    def test_resume_only_runs_missing_action(self, observe, frames):
        saved = {"stage": "adult", "confidence": "high"}
        state, result = worker.infer({}, "mac-metal", "local", saved, self.fail)
        self.assertEqual(state, "complete")
        self.assertEqual(result["action"], "stands with folded arms")
        self.assertEqual(result["code"], worker.VERBS["stands"])
        self.assertEqual(observe.call_count, 1)
        self.assertIs(observe.call_args.args[3], worker.ACTION_PROMPT)

    @patch.object(worker, "frames", return_value=[])
    def test_tiny_face_is_withheld_without_inference(self, frames):
        with patch.object(worker, "observe") as observe:
            state, _ = worker.infer({}, "rtx3070", "local", {}, self.fail)
            self.assertEqual(state, "withheld")
            observe.assert_not_called()
