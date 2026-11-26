"""Regression cases for grounding and rendering saved OpenLABEL scenes."""
import unittest

from openlabel_album import build_scene, card


class OpenLabelAlbumTests(unittest.TestCase):
    def setUp(self):
        self.first = dict(namespace="immich", face_id="f1", person_id="p1")
        self.second = dict(namespace="photo-index", face_id="f2", person_id=None)
        self.regions = {("immich", "f1"): dict(person_id="p1", box=[0, 0, .25, .5]),
                        ("photo-index", "f2"): dict(person_id=None, box=[.5, .5, .75, 1])}
        self.parts = [self.first, " ", "holds ", self.second, " outdoors."]
        self.names = {"p1": "Sam", "photo-index:f2": "Jo"}

    def scene(self):
        return build_scene("a", [self.parts], self.regions, 200, 100)

    def test_rename_and_local_face_keep_roles_and_geometry(self):
        scene = self.scene()
        before = card(scene, self.names)
        actor = before["claims"][0]["roles"]["actor"]
        held = before["claims"][0]["roles"]["held_person"]
        self.assertEqual(before["faces"][held]["name"], "Jo")
        self.assertEqual(before["faces"][actor]["box"], [25, 25, 50, 50])
        self.names["p1"] = "Alex"
        after = card(scene, self.names)
        self.assertEqual(before["claims"], after["claims"])
        self.assertEqual(after["faces"][actor]["name"], "Alex")

    def test_reassignment_and_unbound_recipient(self):
        self.parts = [self.first, " holds a bag."]
        with self.assertRaisesRegex(ValueError, "explicit held face"):
            self.scene()
        self.regions["immich", "f1"]["person_id"] = "changed"
        with self.assertRaisesRegex(ValueError, "assignment changed"):
            self.scene()

    def test_role_swap_and_duplicate_actions(self):
        scene = self.scene()
        roles = scene["openlabel"]["relations"].values()
        for r in roles:
            r["type"] = {"actor": "held_person", "held_person": "actor"}[r["type"]]
        with self.assertRaisesRegex(ValueError, "actor disagree"):
            card(scene, self.names)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            build_scene("a", [self.parts, self.parts], self.regions, 100, 100)
