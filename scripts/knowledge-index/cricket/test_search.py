"""Corrected search publication replaces old memberships and isolates owners."""

import tempfile
import unittest
from pathlib import Path

import duckdb

from cricket.ledger import Ledger
from cricket.search import build_index, categories, search
from cricket.test_ledger import delivery


class SearchTests(unittest.TestCase):
    def test_corrections_dismissal_restore_and_multiple_events_publish_effectively(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = Ledger(root / "ledger.sqlite3")
            ledger.add_album("o", "a", "person-a")
            ledger.add_asset("o", "a", "v", "video", 120, "v1", "original.mp4")
            first = ledger.create_event("o", "a", "v", delivery())
            second = ledger.create_event(
                "o",
                "a",
                "v",
                delivery(start=60, end=80, delivery_start=65, outcome_end=75),
            )
            people = {"person-a": "Test batter"}
            self.assertEqual(len(search(ledger, people, "o", "a", category="four")), 2)
            row = ledger.get("o", first)
            ledger.revise("o", first, row["revision"], patch={"outcome": "six"})
            self.assertEqual(len(search(ledger, people, "o", "a", category="four")), 1)
            self.assertEqual(len(search(ledger, people, "o", "a", category="six")), 1)
            row = ledger.get("o", second)
            hidden = ledger.revise("o", second, row["revision"], action="dismiss")
            self.assertEqual(search(ledger, people, "o", "a", category="four"), [])
            self.assertEqual(search(ledger, people, "another-owner", "a"), [])
            self.assertEqual(len(search(ledger, people, "o", "a", "test SIX")), 1)
            for generation, expected in [("one", 1), ("two", 2)]:
                if generation == "two":
                    ledger.revise("o", second, hidden["revision"], action="restore")
                target = root / generation
                target.mkdir()
                with duckdb.connect() as db:
                    build_index(db, target, root)
                    self.assertEqual(
                        db.execute(
                            "SELECT count(*) FROM read_parquet(?)",
                            [str(target / "cricket_highlights.parquet")],
                        ).fetchone()[0],
                        expected,
                    )
                    self.assertEqual(
                        db.execute(
                            "SELECT count(*) FROM read_parquet(?) WHERE outcome='four'",
                            [str(target / "cricket_highlights.parquet")],
                        ).fetchone()[0],
                        expected - 1,
                    )
            self.assertIn(
                "event=", search(ledger, people, "o", "a")[0]["highlight_url"]
            )
            with self.assertRaises(ValueError):
                search(ledger, people, "o", "a", category="invalid")
            with self.assertRaises(ValueError):
                search(ledger, people, "o", "a", "x" * 201)

    def test_actor_and_wicket_credit_filters_and_disabled_index(self) -> None:
        self.assertEqual(categories(delivery(actor="other"), "person-a"), [])
        self.assertEqual(
            categories(
                delivery(actor=None, role="bowling", outcome="dismissal"), "person-a"
            ),
            ["bowling", "bowling_wicket"],
        )
        self.assertEqual(
            categories(
                delivery(role="bowling", outcome="run_out", wicket_credit="run_out"),
                "person-a",
            ),
            ["bowling", "bowling_wicket"],
        )
        with tempfile.TemporaryDirectory() as directory, duckdb.connect() as db:
            root = Path(directory)
            build_index(db, root, root / "absent")
            self.assertEqual(
                db.execute("SELECT count(*) FROM idx_cricket_highlights").fetchone()[0],
                0,
            )


if __name__ == "__main__":
    unittest.main()
