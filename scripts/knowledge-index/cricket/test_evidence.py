"""Temporal evidence covers whole clips and does not conflate silence with failure."""

import base64
import io
import json
import tempfile
import unittest
from itertools import pairwise
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from cricket.evidence import (
    audio_evidence,
    extract,
    fingerprint,
    positions,
    segments,
    windows,
)
from cricket.prepare import prepare
from cricket.prepare_photos import prepared_photo


class EvidenceTests(unittest.TestCase):
    def test_existing_photo_preview_is_bounded_and_records_provenance(self) -> None:
        source = io.BytesIO()
        Image.new("RGB", (1600, 800)).save(source, "PNG")
        asset = {"id": "photo", "kind": "photo", "fingerprint": "original"}
        result = prepared_photo(asset, None, source.getvalue())
        self.assertEqual(result["source"], "immich-existing-preview")
        self.assertEqual(
            result["cache_key"], fingerprint({"asset": asset, "audio": None})
        )
        with Image.open(
            io.BytesIO(base64.b64decode(result["windows"][0]["frames"][0]))
        ) as preview:
            self.assertEqual(preview.size, (768, 384))

    def test_preparation_cache_is_resumable_and_tracks_audio_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            asset = {
                "id": "video",
                "kind": "video",
                "duration": 30,
                "fingerprint": "v1",
                "locator": "clip.mp4",
            }
            with patch("cricket.prepare.subprocess.run") as run:
                run.return_value.returncode = 0
                run.return_value.stdout = json.dumps(
                    {
                        "version": "cricket-evidence-v1",
                        "windows": [
                            {
                                "start": 0,
                                "end": 30,
                                "positions": [1],
                                "frames": ["anBlZw=="],
                            }
                        ],
                    }
                )
                self.assertEqual(
                    prepare(asset, host="fixture", folder=folder, audio=None)["state"],
                    "prepared",
                )
                self.assertEqual(
                    prepare(asset, host="fixture", folder=folder, audio=None)["state"],
                    "reused",
                )
                self.assertEqual(run.call_count, 1)
                self.assertEqual(
                    prepare(
                        asset,
                        host="fixture",
                        folder=folder,
                        audio={"audio_state": "no_audio"},
                    )["state"],
                    "prepared",
                )
                run.return_value.returncode = 1
                with self.assertRaises(RuntimeError):
                    prepare(
                        {**asset, "id": "failed"},
                        host="fixture",
                        folder=folder,
                        audio=None,
                    )
                self.assertFalse((folder / "failed.json").exists())

    def test_windows_cover_long_clip_and_boundaries(self) -> None:
        spans = windows(410)
        self.assertEqual(spans[0], (0, 30))
        self.assertEqual(spans[-1][1], 410)
        for first, second in pairwise(spans):
            self.assertEqual(first[1] - second[0], 10)
        self.assertEqual(windows(0.5), [(0, 0.5)])
        for duration in (0, -1, float("inf")):
            with self.assertRaises(ValueError):
                windows(duration)
        with self.assertRaises(ValueError):
            windows(30, overlap=30)
        samples = positions(20, 50)
        self.assertGreater(samples[0], 20)
        self.assertLess(samples[-1], 50)
        with self.assertRaises(ValueError):
            positions(1, 1)

    def test_audio_offsets_deduplication_and_bad_segments(self) -> None:
        raw = [
            {"start": 1, "end": 2, "text": "four"},
            {"start": 1, "end": 2, "text": "four"},
            {"start": 50, "end": 51, "text": "six"},
            {},
            {"start": 0, "end": 1, "text": ""},
            {"start": "bad", "end": 2, "text": "bad"},
            {"start": float("nan"), "end": 2, "text": "bad"},
        ]
        self.assertEqual(
            segments(raw, 100, 130, 100), [{"start": 101, "end": 102, "text": "four"}]
        )
        self.assertEqual(audio_evidence(None, 0, 30)["state"], "unavailable")
        self.assertEqual(
            audio_evidence({"audio_state": "no_audio"}, 0, 30)["state"], "no_audio"
        )
        self.assertEqual(
            audio_evidence(
                {"audio_state": "speech", "transcript": json.dumps(raw[:2])}, 0, 30
            )["segments"],
            [{"start": 1, "end": 2, "text": "four"}],
        )

    def test_extract_verifies_source_and_bounded_decoding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "clip.mp4"
            source.write_bytes(b"fixture")
            stat = source.stat()
            packet = {
                "library": directory,
                "locator": "clip.mp4",
                "fingerprint": f"stat:{stat.st_size}:{stat.st_mtime_ns}",
                "kind": "video",
                "duration": 31,
            }
            with patch("cricket.evidence.subprocess.run") as run:
                run.return_value.stdout = b"jpeg"
                result = extract(packet)
                self.assertEqual(len(result["windows"]), 2)
                self.assertEqual(run.call_count, 16)
                self.assertIn("-threads", run.call_args.args[0])
                run.side_effect = [
                    SimpleNamespace(stdout=b""),
                    SimpleNamespace(stdout=b"jpeg"),
                ]
                short = extract({**packet, "duration": 0.25})["windows"][0]
                self.assertEqual(short["positions"], [0.0])
                self.assertEqual(short["missing_frames"], 1)
                run.side_effect = None
                run.return_value.stdout = b""
                with self.assertRaises(ValueError):
                    extract(packet)
            with self.assertRaises(ValueError):
                extract({**packet, "fingerprint": "changed"})
            with self.assertRaises(ValueError):
                extract({**packet, "locator": "../other"})
            with patch("cricket.evidence.subprocess.run") as run:
                run.return_value.stdout = b"jpeg"
                result = extract({**packet, "kind": "photo"})
                self.assertEqual(result["windows"][0]["positions"], [None])
            self.assertNotEqual(
                fingerprint(packet), fingerprint({**packet, "duration": 32})
            )


if __name__ == "__main__":
    unittest.main()
