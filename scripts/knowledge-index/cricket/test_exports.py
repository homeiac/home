"""A real synthetic audio/video export respects corrected bounds and leaves originals intact."""

import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cricket.exports import create, target


@unittest.skipUnless(
    shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg tools required"
)
class ExportTests(unittest.TestCase):
    def test_export_duration_audio_cache_and_revision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.mp4"
            subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "testsrc2=size=160x120:rate=12",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=440",
                    "-t",
                    "3",
                    "-c:v",
                    "libx264",
                    "-threads",
                    "1",
                    "-c:a",
                    "aac",
                    str(source),
                ],
                check=True,
                capture_output=True,
            )
            before = hashlib.sha256(source.read_bytes()).hexdigest()
            event = {
                "id": "e",
                "asset": "v",
                "revision": 1,
                "fingerprint": "fixture",
                "data": {"start": 0.5, "end": 1.5},
            }
            output = create(event, source, root / "exports")
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_streams",
                    "-show_format",
                    "-of",
                    "json",
                    str(output),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            probe = json.loads(result.stdout)
            self.assertAlmostEqual(float(probe["format"]["duration"]), 1, delta=0.15)
            self.assertEqual(
                {s["codec_type"] for s in probe["streams"]}, {"audio", "video"}
            )
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)
            self.assertEqual(
                json.loads(output.with_suffix(".json").read_text())["start"], 0.5
            )
            with patch(
                "cricket.exports.subprocess.run",
                side_effect=AssertionError("cache should be reused"),
            ):
                self.assertEqual(create(event, source, root / "exports"), output)
            self.assertNotEqual(
                target({**event, "revision": 2}, root / "exports"), output
            )
            with self.assertRaises(ValueError):
                create(
                    {**event, "data": {"start": None, "end": None}},
                    source,
                    root / "exports",
                )


if __name__ == "__main__":
    unittest.main()
