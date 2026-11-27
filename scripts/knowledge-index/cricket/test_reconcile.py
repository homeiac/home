"""Reruns preserve corrections and do not confuse padded clips with distinct deliveries."""

import tempfile
import unittest
from pathlib import Path

from cricket.ledger import Conflict, Ledger
from cricket.reconcile import deduplicate, reconcile, same_delivery
from cricket.test_ledger import delivery


def observation(at: float = 30, outcome: str = "four") -> dict:
    return {
        "data": delivery(
            delivery_start=at,
            outcome_end=at + 8,
            start=max(0, at - 10),
            end=at + 13,
            outcome=outcome,
        ),
        "observed_start": at,
        "observed_end": at + 8,
        "evidence": {"confidence": "possible"},
    }


class ReconcileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ledger = Ledger(Path(self.temp.name) / "db")
        self.ledger.add_album("o", "a", "person-a")
        self.ledger.add_asset("o", "a", "v", "video", 120, "v1")

    def save(self, items: list, run: str = "r1", fingerprint: str = "v1") -> dict:
        return reconcile(
            self.ledger,
            "o",
            "a",
            "v",
            fingerprint,
            items,
            model="fixture",
            version="v1",
            run=run,
        )

    def test_correction_dismissal_and_identity_survive_jitter_and_restart(self) -> None:
        self.save([observation()])
        event = self.ledger.list_events("o", "a")[0]
        edited = self.ledger.revise(
            "o",
            event["id"],
            event["revision"],
            patch={"outcome": "six", "actor": None, "start": 12},
        )
        self.ledger.revise("o", event["id"], edited["revision"], action="dismiss")
        self.save([observation(31, "other")], "r2")
        row = Ledger(self.ledger.path).list_events("o", "a", True)[0]
        self.assertEqual(row["id"], event["id"])
        self.assertTrue(row["dismissed"])
        self.assertEqual(
            (row["data"]["outcome"], row["data"]["actor"], row["data"]["start"]),
            ("six", None, 12),
        )
        self.assertEqual(self.ledger.list_events("o", "a"), [])

    def test_retry_and_overlapping_windows_do_not_duplicate_events(self) -> None:
        values = [observation(30), observation(31), observation(38)]
        self.save(values)
        self.save(values)
        self.assertEqual(len(self.ledger.list_events("o", "a")), 2)
        self.assertEqual(
            deduplicate([observation(30, "four"), observation(31, "six")])[0]["data"][
                "outcome"
            ],
            "boundary_unclear",
        )
        self.assertEqual(
            deduplicate([observation(30, "unknown"), observation(31, "four")])[0][
                "data"
            ]["outcome"],
            "four",
        )
        with self.assertRaises(Conflict):
            self.save([observation(30, "six")])

    def test_ambiguous_split_preserves_reviewed_event(self) -> None:
        self.save([observation(30)])
        row = self.ledger.list_events("o", "a")[0]
        self.ledger.revise("o", row["id"], row["revision"], action="accept")
        result = self.save([observation(28.1), observation(31.9)], "r2")
        self.assertEqual(result["ambiguous"], 2)
        self.assertEqual(len(self.ledger.list_events("o", "a")), 1)
        self.assertEqual(self.ledger.get("o", row["id"])["review_state"], "confirmed")

    def test_unmatched_reviewed_events_stay_unreviewed_ones_are_superseded(
        self,
    ) -> None:
        self.save([observation(30), observation(80)])
        row = self.ledger.list_events("o", "a")[0]
        self.ledger.revise("o", row["id"], row["revision"], patch={"outcome": "six"})
        self.assertEqual(self.save([], "r2")["superseded"], 1)
        self.assertEqual(len(self.ledger.list_events("o", "a")), 1)
        self.save([observation(80)], "r3")
        self.assertEqual(len(self.ledger.list_events("o", "a")), 2)

    def test_source_changes_and_invalid_batches_are_atomic(self) -> None:
        with self.assertRaises(Conflict):
            self.save([observation()], fingerprint="v2")
        with self.assertRaises(ValueError):
            self.save([observation(), observation(119)])
        self.assertEqual(self.ledger.list_events("o", "a"), [])

    def test_activity_matching_and_invalid_observed_interval(self) -> None:
        first, second = observation(), observation(31)
        first["data"]["delivery_start"] = None
        self.assertFalse(same_delivery(first, second))
        second["data"]["delivery_start"] = None
        self.assertTrue(same_delivery(first, second))
        second["observed_start"], second["observed_end"] = 80, 88
        self.assertFalse(same_delivery(first, second))
        first["observed_start"] = -1
        with self.assertRaises(ValueError):
            self.save([first])
        self.assertEqual(self.ledger.list_events("o", "a"), [])

    def test_incompatible_new_bounds_preserve_corrected_interval(self) -> None:
        self.save([observation()])
        event = self.ledger.list_events("o", "a")[0]
        self.ledger.revise("o", event["id"], event["revision"], patch={"start": 40})
        candidate = observation(30)
        candidate["data"]["end"] = 39
        self.assertEqual(self.save([candidate], "r2")["incompatible"], 1)
        self.assertEqual(self.ledger.get("o", event["id"])["data"]["end"], 43)


if __name__ == "__main__":
    unittest.main()
