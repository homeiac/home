"""Participant verification, chronology and component boundaries across arbitrary assets."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PIL import Image, ImageDraw

from caption_participants import age_status, attach, candidate_phrases, fingerprint
from chronological_highlights import select_highlights
from collage_catalogue import catalogue, project, regular_grid
from openlabel_album import build_scene, card
from scan_caption_participants import infer


class ParticipantTests(unittest.TestCase):
    def setUp(self):
        self.refs = [
            dict(
                namespace="immich",
                face_id=f"face{i}",
                person_id=None,
                box=[x, 0.2, x + 0.12, 0.45],
            )
            for i, x in enumerate([0.1, 0.7])
        ]
        self.regions = {(r["namespace"], r["face_id"]): r for r in self.refs}
        self.scene = build_scene(
            "asset",
            [],
            {},
            100,
            50,
            {"scene": "Two people sit.", "reason": "ambiguous"},
        )

    def test_unclustered_face_survives_later_naming(self):
        decision = {
            "caption_hash": fingerprint(["Two people sit."]),
            "mentions": [{"words": "Two people", "faces": self.refs}],
        }
        self.regions["immich", "face0"] = dict(self.refs[0], person_id="cluster")
        attach(self.scene, "asset", ["Two people sit."], self.regions, decision)
        photo = card(self.scene, {"cluster": "Renamed"})
        self.assertEqual(len(photo["mentions"][0]["faces"]), 2)
        self.assertEqual(
            {f["name"] for f in photo["faces"].values()}, {"Renamed", "Unnamed person"}
        )
        with self.assertRaisesRegex(ValueError, "Caption changed"):
            attach(self.scene, "asset", ["Two people wave."], self.regions, decision)

    def test_consensus_with_different_box_numbers_and_off_camera_guard(self):
        with TemporaryDirectory() as d:
            im = Path(d) / "sample.jpg"
            Image.new("RGB", (100, 100)).save(im)
            job = dict(
                captions=["sits with another person"], regions=self.refs, image=im
            )

            def scan(numbers):
                sequence = iter(numbers)
                return infer(
                    job,
                    lambda *_: {
                        "mentions": [
                            {
                                "words": "another person",
                                "boxes": next(sequence),
                                "certain": True,
                            }
                        ]
                    },
                )["mentions"][0]["faces"]

            self.assertEqual(scan([[2], [3]]), [self.refs[1]])
            self.assertEqual(scan([[2], [4]]), [])
            self.assertEqual(scan([[1, 2], [3, 4]]), [])
            job["captions"] = ["holds hands with another person"]
            self.assertEqual(scan([[2], [3]]), [])
            job["verified_roles"] = {"another person": ["face1"]}
            self.assertEqual(scan([[2], [3]]), [self.refs[1]])
            self.assertEqual(
                candidate_phrases(["walks next to another woman"]), ["another woman"]
            )

    def test_grid_requires_consistent_gutters(self):
        image = Image.new("RGB", (300, 200), "black")
        draw = ImageDraw.Draw(image)
        for x in (100, 200):
            draw.line((x, 0, x, 200), fill="white", width=2)
        draw.line((0, 100, 300, 100), fill="white", width=2)
        self.assertEqual(len(regular_grid(image)["panels"]), 6)
        draw.line((10, 0, 10, 200), fill="white")
        self.assertIsNone(regular_grid(image))

    def test_component_actions_cannot_cross_photos(self):
        left = {"polygon": [[0, 0], [0.5, 0], [0.5, 1], [0, 1]], "actions": []}
        right = {
            "polygon": [[0.5, 0], [1, 0], [1, 1], [0.5, 1]],
            "actions": [{"code": "ACT.008", "text": "Looks up.", "actors": ["face1"]}],
        }
        catalogue(self.scene, "asset", {"panels": [left, right]}, self.regions)
        _, panels = project(self.scene["openlabel"])
        self.assertEqual(panels[1]["actions"][0]["actors"], panels[1]["faces"])
        self.assertTrue(set(panels[0]["faces"]).isdisjoint(panels[1]["faces"]))
        right["actions"][0]["actors"] = ["face0"]
        with self.assertRaisesRegex(ValueError, "outside"):
            catalogue(self.scene, "asset", {"panels": [left, right]}, self.regions)

    def test_confirmed_dates_composites_and_uncertain_dates(self):
        row = dict(
            date="2020-01-01",
            status="compatible",
            accepted={"stage": "preschool", "confidence": "high"},
        )
        self.assertEqual(age_status(row, 2000), "conflict")
        self.assertEqual(age_status(dict(row, composite=True), 2000), "composite")
        self.assertEqual(age_status(dict(row, status="unresolved"), 2000), "unresolved")
        self.assertEqual(
            age_status(dict(row, owner={"confirmed_capture_date": row["date"]}), 2000),
            "confirmed",
        )
        candidate = dict(
            id="first", date=row["date"], local=True, native=True, caption=True
        )
        self.assertEqual(
            select_highlights([candidate], {"first": {"type": "Collage"}}), []
        )
