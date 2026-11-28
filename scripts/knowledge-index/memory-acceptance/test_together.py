"""A shared journey must be supported independently for every requested person."""

import unittest

from review_openlabel import select_together, render_review


class TogetherTests(unittest.TestCase):
    def test_exact_subjects_and_stable_order(self) -> None:
        item = {"media_type": "Photo", "date": "2010-01-01", "date_status": "conflict",
                "date_conflict": {"birth_year": "1990"},
                "faces": {"a": {"person_id": "1"}, "b": {"person_id": "2"}, "c": {"person_id": "3"}},
                "claims": [{"subject": "a"}], "individual": [{"subject": "b"}]}
        cards = {asset: dict(item, asset=asset) for asset in ["z", "a"]}
        cards.update({"c": dict(item, asset="c", individual=[]),
                      "d": dict(item, asset="d", media_type="Collage"),
                      "e": dict(item, asset="e", media_type="Embedded photo")})
        selection = select_together(cards, ["1", "2"])
        self.assertEqual([r["asset"] for r in selection], ["a", "z"])
        self.assertEqual(selection, select_together(cards, ["2", "1"]))
        self.assertFalse(select_together(cards, ["1", "3"]))
        self.assertNotIn("date_conflict", selection[0])
        self.assertIn("conflict", selection[0]["journey_date_note"])
        self.assertIn("date_conflict", cards["a"])
        with self.assertRaises(ValueError):
            select_together(cards, ["1", "1"])

    def test_page_escapes_directory_names_and_literal_captions(self) -> None:
        page = render_review("REVIEW_TITLE REVIEW_INTRO PILOT_JSON", [{"scene": "</script>"}], "A&B", "OK")
        self.assertIn("A&amp;B OK", page)
        self.assertNotIn("</script>", page)
