"""Network and guest transports are mocked; no private model credential is used."""

import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cricket.models import infer
from cricket.trial import analyze_one


class ModelTests(unittest.TestCase):
    def test_local_and_remote_response_formats(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            key = Path(folder) / "key"
            key.write_text("synthetic-fixture")
            backend = {
                "endpoint": "http://fixture",
                "api": "openai",
                "model": "fixture",
                "key_file": str(key),
            }
            with patch(
                "cricket.models.urllib.request.urlopen",
                return_value=io.BytesIO(
                    b'{"choices":[{"message":{"content":"answer"}}]}'
                ),
            ) as call:
                self.assertEqual(infer(backend, "prompt", ["frame"]), "answer")
                self.assertEqual(
                    call.call_args.args[0].headers["Authorization"],
                    "Bearer synthetic-fixture",
                )
            backend.update(transport="ssh", host="fixture", api="ollama")
            with patch("cricket.models.subprocess.run") as run:
                run.return_value = SimpleNamespace(
                    returncode=0, stdout='{"message":{"content":"answer"}}'
                )
                self.assertEqual(infer(backend, "prompt", []), "answer")
                run.return_value.returncode = 1
                with self.assertRaises(RuntimeError):
                    infer(backend, "prompt", [])
            backend.update(transport="qga", api="openai")
            with patch("cricket.models.subprocess.run") as run:
                run.return_value = SimpleNamespace(
                    returncode=0,
                    stdout=json.dumps(
                        {
                            "exited": True,
                            "exitcode": 0,
                            "out-data": '{"choices":[{"message":{"content":"answer"}}]}',
                        }
                    ),
                )
                self.assertEqual(infer(backend, "prompt", []), "answer")
                run.return_value.stdout = '{"exited":false}'
                with self.assertRaises(RuntimeError):
                    infer(backend, "prompt", [])
                run.return_value.returncode = 1
                with self.assertRaises(RuntimeError):
                    infer(backend, "prompt", [])
            with self.assertRaises(ValueError):
                infer({**backend, "transport": "invalid"}, "prompt", [])

    def test_partial_model_errors_do_not_discard_valid_events(self) -> None:
        row = {
            "asset": {"kind": "video", "duration": 60},
            "window": {
                "start": 0,
                "end": 30,
                "positions": [1],
                "frames": ["frame"],
                "audio": {"state": "no_audio", "segments": []},
            },
        }
        with patch(
            "cricket.trial.infer",
            return_value='{"events":[{"role":"batting"},{"runup_start":90}]}',
        ):
            result = analyze_one(row, {}, "a", "portrait")
            self.assertEqual(len(result["proposals"]), 1)
            self.assertEqual(len(result["invalid_events"]), 1)
        with (
            patch(
                "cricket.trial.infer", return_value='{"events":[{"runup_start":90}]}'
            ),
            self.assertRaises(ValueError),
        ):
            analyze_one(row, {}, "a", None)
        with patch("cricket.trial.infer", return_value='{"events":[]}'):
            self.assertEqual(analyze_one(row, {}, "a", None)["proposals"], [])


if __name__ == "__main__":
    unittest.main()
