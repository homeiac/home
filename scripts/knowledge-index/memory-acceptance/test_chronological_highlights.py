import unittest

from chronological_highlights import select_highlights


class SelectionTests(unittest.TestCase):
    def test_evidence_order_gaps_and_replay(self):
        base = dict(local=True, native=True, caption=True, reason=None)
        def row(key, day, **fields):
            return dict(base, id=key, date=day) | fields
        rows = [row("early", "2001-01-01", local=False, caption=False),
                row("two-sources", "2002-03-30"), row("local", "2002-03-01", native=False),
                row("no-text", "2002-01-01", caption=False), row("later", "2002-12-20"),
                row("undated", None), row("excluded", "2003-01-01", reason="copy"),
                row("unconfirmed", "2004-01-01", local=False, native=False)]
        self.assertEqual([r["id"] for r in select_highlights(rows)], ["early", "two-sources", "later"])
        self.assertEqual(select_highlights(rows[::-1]), select_highlights(rows))

    def test_duplicate_mapping_requires_upstream_resolution(self):
        row = dict(id="same", date="2001-01-01", local=True, native=False, caption=False)
        with self.assertRaises(ValueError):
            select_highlights([row, row])
