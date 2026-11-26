import unittest

from action_gate import Action, publishable_action


class ActionGateTests(unittest.TestCase):
    def test_holding_direction_requires_agreement(self):
        adult_holds_child = Action("adult", "holds", recipient="child")
        child_holds_adult = Action("child", "holds", recipient="adult")
        self.assertIsNone(publishable_action(
            "adult", {"adult", "child"}, {"local": child_holds_adult, "reviewer": adult_holds_child}
        ))
        self.assertEqual(publishable_action(
            "adult", {"adult", "child"}, {"local": adult_holds_child, "reviewer": adult_holds_child}
        ), adult_holds_child)

    def test_one_model_and_unknown_identity_are_insufficient(self):
        riding = Action("1", "sits", object="scooter")
        self.assertIsNone(publishable_action("1", {"1"}, {"local": riding, "reviewer": None}))
        self.assertIsNone(publishable_action("1", set(), {"local": riding, "reviewer": riding}))

    def test_disagreement_on_contact_is_held_for_review(self):
        sits = Action("1", "sits", object="scooter")
        rides = Action("1", "rides", object="scooter")
        self.assertIsNone(publishable_action("1", {"1"}, {"local": rides, "reviewer": sits}))
        self.assertEqual(publishable_action("1", {"1"}, {"local": rides}, reviewed=sits), sits)
        self.assertIsNone(publishable_action("2", {"1", "2"}, {}, reviewed=sits))
