"""Exercise per-face coverage using only synthetic assets."""

import unittest

from journey_faces import complete_faces
from openlabel_album import build_scene, card, stable_id


class JourneyFaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.a = dict(namespace="immich", face_id="a", person_id="p", box=[0, 0, .25, .5])
        self.b = dict(namespace="immich", face_id="b", person_id=None, box=[.5, 0, 1.1, .5])
        self.regions = {("immich", f["face_id"]): f for f in [self.a, self.b]}
        self.scene = build_scene("asset", [[self.a, " sits here."]], self.regions, 100, 100)
        self.subjects = {stable_id("asset", "immich", "a")}

    def test_distinct_actor_target_and_clipped_box(self) -> None:
        review = dict(box=self.b["box"], action="holds {person} on the sofa.",
                      target="a", target_box=self.a["box"])
        complete_faces(self.scene, "asset", self.regions, self.subjects, {"b": review})
        result = card(self.scene, {"p": "Jo"})
        extra, = result["individual"]
        actor = extra["subject"]
        verb, = (s for s in extra["spans"] if "verb" in s)
        self.assertEqual(verb["roles"], {"actor": actor, "held_person": next(iter(self.subjects))})
        self.assertEqual(result["faces"][actor]["box"], [75, 25, 50, 50])
        self.assertTrue(result["faces"][actor]["unnamed"])
        self.assertEqual(len(result["claims"]), 1)

    def test_stale_review_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "box changed"):
            complete_faces(self.scene, "asset", self.regions, self.subjects, {"b": {"box": self.a["box"]}})

    def test_missing_review_keeps_the_face_and_withholds_the_action(self) -> None:
        complete_faces(self.scene, "asset", self.regions, self.subjects, {})
        result = card(self.scene, {})
        self.assertFalse(result["individual"])
        self.assertIn("not been reviewed", result["faces"][stable_id("asset", "immich", "b")]["action_withheld"])
