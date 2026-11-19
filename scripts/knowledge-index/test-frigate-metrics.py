#!/usr/bin/env python3
"""Verify Frigate telemetry preserves unavailable, idle and active distinctions."""
import io
import json
from pathlib import Path
import runpy
import unittest
from unittest.mock import patch

module = runpy.run_path(str(Path(__file__).with_name("export-frigate-metrics.py")))


class FrigateMetricsTests(unittest.TestCase):
    def collect(self, data):
        with patch("urllib.request.OpenerDirector.open", return_value=io.BytesIO(json.dumps(data).encode())):
            return module["collect"]("https://frigate.example")

    def test_native_processing_and_no_private_labels(self):
        text = self.collect({"detectors": {"cpu": {"inference_speed": 42.5}},
                             "detection_fps": 6.8, "embeddings": {"face_recognition_speed": 0},
                             "cameras": {"private-camera-name": {}}, "private": "person-name"})
        self.assertIn('title="Frigate API (1=up)"} 1', text)
        self.assertIn('title="Frigate object detector (ms)"} 42.5', text)
        self.assertIn('title="Frigate face recognition (ms)"} 0', text)
        self.assertIn('frames_per_second{kind="objects"} 6.8', text)
        self.assertNotIn("private-camera-name", text)
        self.assertNotIn("person-name", text)

    def test_missing_and_invalid_values_are_not_idle_zero(self):
        text = self.collect({"detectors": {"cpu": {"inference_speed": -1}}, "embeddings": None})
        self.assertNotIn('photo_frigate_processing_milliseconds{', text)
        self.assertNotIn('photo_frigate_frames_per_second{', text)
        self.assertIn('title="Frigate API (1=up)"} 1', text)

    def test_unreachable_service(self):
        with patch("urllib.request.OpenerDirector.open", side_effect=TimeoutError):
            text = module["collect"]("https://frigate.example")
        self.assertIn('title="Frigate API (1=up)"} 0', text)
        self.assertNotIn('photo_frigate_processing_milliseconds{', text)

    def test_unexpected_schema(self):
        text = self.collect({"message": "login required"})
        self.assertIn('title="Frigate API (1=up)"} 0', text)


if __name__ == "__main__":
    unittest.main()
