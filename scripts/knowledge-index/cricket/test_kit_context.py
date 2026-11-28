"""Kit clues are bounded by recording date and use effective identity corrections."""

import tempfile
import unittest
from pathlib import Path

from cricket.kit_context import kit, nearby
from cricket.ledger import Ledger
from cricket.test_ledger import delivery


class KitTests(unittest.TestCase):
    def test_numbers_colors_and_nearby_corrected_identities(self) -> None:
        self.assertEqual(
            kit({"jersey_colors": ["Blue", "blue", "invented"], "jersey_number": "?"}),
            {"jersey_colors": ["blue"], "jersey_number": None},
        )
        with tempfile.TemporaryDirectory() as directory:
            ledger = Ledger(Path(directory) / "ledger")
            ledger.add_album("o", "a", "person-a")
            ledger.add_asset("o", "a", "v", "video", 120, "same")
            event = ledger.create_event("o", "a", "v", delivery())
            ledger.propose(
                "o",
                event,
                delivery(),
                evidence={
                    "identity_context": {
                        "recorded_date": "2021-05-01",
                        "status": "known",
                    },
                    "subject_kit": {"jersey_colors": ["blue"], "jersey_number": "7"},
                    "identity_basis": "user_album_rule",
                },
                model="fixture",
                version="v",
                run="r",
            )
            context = {"recorded_date": "2021-05-15", "status": "known"}
            self.assertEqual(
                nearby(ledger, "o", "a", "person-a", "next", context)[0][
                    "jersey_number"
                ],
                "7",
            )
            self.assertEqual(nearby(ledger, "o", "a", "person-a", "v", context), [])
            self.assertEqual(
                nearby(ledger, "another", "a", "person-a", "next", context), []
            )
            self.assertEqual(
                nearby(
                    ledger,
                    "o",
                    "a",
                    "person-a",
                    "next",
                    {**context, "recorded_date": "2022-05-15"},
                ),
                [],
            )
            self.assertEqual(
                nearby(ledger, "o", "a", "person-a", "next", {"status": "unavailable"}),
                [],
            )
            current = ledger.get("o", event)
            ledger.revise("o", event, current["revision"], patch={"actor": None})
            self.assertEqual(nearby(ledger, "o", "a", "person-a", "next", context), [])


if __name__ == "__main__":
    unittest.main()
