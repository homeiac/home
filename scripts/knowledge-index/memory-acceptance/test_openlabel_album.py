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

    def test_compound_after_another_face_keeps_original_actor(self):
        self.parts = [self.first, " rests in ", self.second, "’s arms and looks to the side."]
        scene = self.scene()
        result, = card(scene, self.names)["claims"]
        verbs = [s for s in result["spans"] if "verb" in s]
        self.assertEqual([s["verb"] for s in verbs], ["rests", "looks to the side"])
        self.assertNotEqual(verbs[0]["id"], verbs[1]["id"])
        self.assertEqual(verbs[0]["roles"], verbs[1]["roles"])
        self.assertEqual(verbs[1]["roles"], {"actor": result["spans"][0]["face"]})
        self.assertEqual(verbs[1]["code"], "ACT.008")
        self.assertEqual(scene, self.scene())

    def test_explicit_second_subject_does_not_inherit_the_first_face(self):
        self.parts = [self.first, " rests and ", self.second, " looks to the side."]
        result, = card(self.scene(), self.names)["claims"]
        self.assertEqual([s["verb"] for s in result["spans"] if "verb" in s], ["rests"])

    def test_secondary_anchor_with_recipient_or_inanimate_object(self):
        self.parts = [self.first, " sits beside ", self.second, " with an arm around him."]
        result, = card(self.scene(), self.names)["claims"]
        arm, = [s for s in result["spans"] if s.get("code") == "ACT.010"]
        self.assertEqual(arm["roles"]["recipient"], next(
            s["face"] for s in result["spans"] if "face" in s and s != result["spans"][0]))
        self.parts = [self.first, " sits on the scooter and holds the handlebar."]
        result, = card(self.scene(), self.names)["claims"]
        handle, = [s for s in result["spans"] if s.get("code") == "ACT.009"]
        self.assertEqual(set(handle["roles"]), {"actor"})

    def test_older_scene_keeps_original_single_action(self):
        self.parts = [self.first, " rests in ", self.second, "’s arms and looks to the side."]
        scene = self.scene()
        data = scene["openlabel"]
        data["metadata"]["vocabulary_release"] = "album-1"
        data["actions"] = {k:v for k,v in data["actions"].items() if v["name"] == "rests"}
        data["relations"] = {k:v for k,v in data["relations"].items()
                             if v["rdf_subjects"][0]["uid"] in data["actions"]}
        claim, = card(scene, self.names)["claims"]
        self.assertEqual([s["verb"] for s in claim["spans"] if "verb" in s], ["rests"])

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

    def test_marked_passive_and_active_have_distinct_click_targets(self):
        literal = " is held and smiles."
        review = dict(self.first, literal=literal, spans=[
            dict(start=1, end=8, words="is held", sense="held"),
            dict(start=13, end=19, words="smiles", sense="smile")])
        parts = [[self.first, literal]]

        def build():
            return build_scene("a", parts, self.regions, 200, 100, review)

        claim, = card(build(), self.names)["claims"]
        held, smiles = [s for s in claim["spans"] if "verb" in s]
        self.assertEqual(held["roles"], {"held_person": claim["subject"]})
        self.assertEqual(smiles["roles"], {"actor": claim["subject"]})
        self.assertNotEqual(held["id"], smiles["id"])
        damaged = build()
        damaged["openlabel"]["actions"]["orphan"] = {
            "name": "wave", "type": "ACT.004", "action_data": {
                "text": [{"name": "source", "val": "marked subject"}]}}
        with self.assertRaisesRegex(ValueError, "clickable span"):
            card(damaged, self.names)
        review["spans"][1]["start"] = 7
        with self.assertRaisesRegex(ValueError, "span"):
            build()
        review["literal"] += "!"
        with self.assertRaisesRegex(ValueError, "caption changed"):
            build()
        review["face_id"] = "different"
        with self.assertRaisesRegex(ValueError, "Marked face"):
            build()

    def test_scene_only_preserves_words_without_personal_actions(self):
        review = {"scene": "Two people sit together.", "reason": "ambiguous face location"}
        scene = build_scene("a", [], self.regions, 200, 100, review)
        result = card(scene, self.names)
        self.assertEqual(result["scene"], review["scene"])
        self.assertEqual(result["reason"], review["reason"])
        self.assertEqual(result["faces"], {})
        self.assertEqual(result["claims"], [])
        with self.assertRaisesRegex(ValueError, "conflicts"):
            build_scene("a", [self.parts], self.regions, 200, 100, review)
