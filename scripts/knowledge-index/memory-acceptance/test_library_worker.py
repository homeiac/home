"""Check malformed responses, two-pass resumption and native action attribution."""

import unittest
from unittest.mock import patch

import library_worker as worker


class LibraryWorkerTests(unittest.TestCase):
    def test_separate_object_is_lossless_and_other_actor_remains_invalid(self):
        self.assertEqual(
            worker.normalized_action({"verb": "holds", "action": "a diploma"}),
            ("holds", "holds a diploma"),
        )
        self.assertEqual(
            worker.normalized_action({"verb": "faces", "action": "the camera"}),
            ("faces", "faces the camera"),
        )
        for action in (
            {"verb": "sits", "action": "a diploma"},
            {"verb": "holds", "action": "the bystander holds a diploma"},
        ):
            with self.subTest(action=action), self.assertRaises(ValueError):
                worker.normalized_action(action)

    @patch("tune_library_worker.subprocess.run")
    def test_failed_trial_restores_worker(self, invoke):
        from tune_library_worker import paused_worker

        invoke.return_value.returncode = 0
        with self.assertRaises(ValueError), paused_worker(True):
            raise ValueError("bad trial")
        self.assertEqual(
            [call.args[0][1] for call in invoke.call_args_list],
            ["print", "bootout", "bootstrap"],
        )

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

    def test_visual_prefix_keeps_both_images_and_question_on_each_transport(self):
        import io
        import json
        from media_summary import ask_model

        for api, reply in (
            ("ollama", {"message": {"content": "answer"}}),
            ("openai", {"choices": [{"message": {"content": "answer"}}]}),
        ):
            for prefix in (False, True):
                with self.subTest(api=api, prefix=prefix), patch(
                    "urllib.request.urlopen",
                    return_value=io.BytesIO(json.dumps(reply).encode()),
                ) as request:
                    self.assertEqual(
                        ask_model(
                            "http://local",
                            "model",
                            "question",
                            [b"a", b"b"],
                            api=api,
                            images_first=prefix,
                        ),
                        "answer",
                    )
                    messages = json.loads(request.call_args.args[0].data)["messages"]
                    if api == "ollama":
                        self.assertEqual(messages[0]["images"], ["YQ==", "Yg=="])
                        self.assertEqual(messages[-1]["content"], "question")
                        self.assertEqual(len(messages), 2 if prefix else 1)
                    else:
                        content = messages[0]["content"]
                        self.assertEqual(
                            content[-1 if prefix else 0]["text"], "question"
                        )
                        self.assertEqual(
                            [
                                x["image_url"]["url"].split(",")[1]
                                for x in content
                                if x["type"] == "image_url"
                            ],
                            ["YQ==", "Yg=="],
                        )
