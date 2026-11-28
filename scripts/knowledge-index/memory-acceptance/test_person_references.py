import unittest

from person_references import PersonRef, caption_parts, resolve_caption


class PersonReferenceTests(unittest.TestCase):
    def test_late_name_and_rename_update_actor_and_recipient(self):
        actor = PersonRef("person-a", "Asha")
        child = PersonRef("person-b", "Nikhil")
        parts = caption_parts("Asha holds Nikhil. Nikhil looks to the side.", {
            "Asha": actor, "Nikhil": child
        })
        self.assertEqual(resolve_caption(parts, {}),
                         "Asha holds Nikhil. Nikhil looks to the side.")
        self.assertEqual(resolve_caption(parts, {"person-a": "Ash", "person-b": "Nik"}),
                         "Ash holds Nik. Nik looks to the side.")

    def test_unnamed_person_can_appear_later(self):
        person = PersonRef("person-new")
        self.assertEqual(person.name({}), "Unnamed person")
        self.assertEqual(person.name({"person-new": "Adil"}), "Adil")

    def test_short_name_only_matches_whole_words(self):
        parts = caption_parts("G stands near Gita. G’s hands are visible.", {
            "G": PersonRef("person-g", "G")
        })
        self.assertEqual(resolve_caption(parts, {"person-g": "Kumar"}),
                         "Kumar stands near Gita. Kumar’s hands are visible.")
