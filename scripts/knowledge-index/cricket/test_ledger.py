"""Synthetic behavior tests for correction durability and source integrity."""

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import MagicMock, patch

from cricket.ledger import Conflict, Ledger, backup, restore


def delivery(**changes: object) -> dict:
    """A fictional 40-second delivery inside a 120-second original."""
    return {
        "actor": "person-a",
        "role": "batting",
        "outcome": "four",
        "wicket_credit": "unknown",
        "start": 20,
        "end": 60,
        "delivery_start": 30,
        "outcome_end": 55,
        **changes,
    }


class LedgerTests(unittest.TestCase):
    def test_read_only_snapshot_sees_wal_and_rejects_writes(self) -> None:
        with self.db.connect() as held:
            held.execute("SELECT count(*) FROM events").fetchone()
            self.revise(patch={"outcome": "six"})
            reader = Ledger(self.path, read_only=True)
            self.assertEqual(reader.get("owner", self.event)["data"]["outcome"], "six")
            with self.assertRaises(PermissionError):
                reader.add_album("owner", "new")
            with reader.connect() as db, self.assertRaises(sqlite3.OperationalError):
                db.execute("DELETE FROM albums")
        with self.assertRaises(sqlite3.OperationalError):
            Ledger(self.path.parent / "absent.sqlite3", read_only=True)
        self.assertFalse((self.path.parent / "absent.sqlite3").exists())
        invalid = self.path.parent / "invalid.sqlite3"
        with sqlite3.connect(invalid):
            pass
        with self.assertRaises(ValueError):
            Ledger(invalid, read_only=True)

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "cricket.sqlite3"
        self.db = Ledger(self.path)
        self.db.add_album("owner", "album", "person-a")
        self.db.add_asset("owner", "album", "video", "video", 120, "original-v1")
        self.event = self.db.create_event("owner", "album", "video", delivery())

    def revise(self, **kwargs: object) -> dict:
        return self.db.revise(
            "owner", self.event, self.db.get("owner", self.event)["revision"], **kwargs
        )

    def propose(self, run: str = "run1", **changes: object) -> dict:
        return self.db.propose(
            "owner",
            self.event,
            delivery(**changes),
            evidence={"confidence": "likely"},
            model="fixture",
            version="v2",
            run=run,
        )

    def test_field_corrections_and_explicit_clear_survive_new_proposals_and_restart(
        self,
    ) -> None:
        self.revise(patch={"outcome": "six", "actor": None, "start": 15})
        result = self.propose(end=65, actor="wrong-person", outcome="other")
        self.assertEqual(
            result["data"], delivery(actor=None, outcome="six", start=15, end=65)
        )
        reopened = Ledger(self.path)
        self.assertEqual(reopened.get("owner", self.event), result)
        self.assertEqual(result["review_state"], "corrected")

    def test_dismiss_restore_and_undo_preserve_history(self) -> None:
        self.revise(action="dismiss")
        self.propose(outcome="six")
        self.assertEqual(self.db.list_events("owner", "album"), [])
        self.assertEqual(len(self.db.list_events("owner", "album", True)), 1)
        self.revise(action="undo")
        self.assertEqual(len(self.db.list_events("owner", "album")), 1)
        self.revise(action="dismiss")
        self.revise(action="restore")
        with self.db.connect() as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM revisions").fetchone()[0], 4
            )

    def test_undo_edit_restores_previous_overrides_with_latest_proposal(self) -> None:
        self.revise(patch={"outcome": "six"})
        self.propose(start=19)
        result = self.revise(action="undo")
        self.assertEqual(result["data"], delivery(start=19))
        self.assertEqual(result["review_state"], "suggested")

    def test_accept_freezes_complete_event(self) -> None:
        self.revise(action="accept")
        result = self.propose(outcome="six", start=19)
        self.assertEqual(result["data"], delivery())
        self.assertEqual(result["review_state"], "confirmed")

    def test_manual_event_survives_model_updates(self) -> None:
        self.event = self.db.create_event(
            "owner", "album", "video", delivery(outcome="six"), manual=True
        )
        self.assertEqual(self.propose()["data"]["outcome"], "six")
        with self.assertRaises(ValueError):
            self.revise(action="undo")
        self.revise(action="dismiss")

    def test_concurrent_or_model_changed_revision_is_rejected(self) -> None:
        old = self.db.get("owner", self.event)["revision"]
        self.propose()
        with self.assertRaises(Conflict):
            self.db.revise("owner", self.event, old, patch={"outcome": "six"})
        with self.assertRaises(Conflict):
            self.db.revise("owner", self.event, True, patch={"outcome": "six"})

    def test_retry_is_idempotent_and_cannot_replace_a_run(self) -> None:
        first = self.propose()
        self.assertEqual(self.propose(), first)
        with self.assertRaises(Conflict):
            self.propose(outcome="six")

    def test_invalid_correction_rolls_back_everything(self) -> None:
        before = self.db.get("owner", self.event)
        for change in (
            {"start": -1},
            {"end": 121},
            {"start": 60},
            {"end": float("nan")},
            {"start": True},
            {"delivery_start": 100},
            {"outcome_end": -1},
            {"outcome": "seven"},
            {"role": "catcher"},
            {"wicket_credit": "bowler"},
            {"wicket_credit": "run_out"},
            {"wicket_credit": "invalid"},
            {"actor": ""},
        ):
            with self.subTest(patch=change), self.assertRaises(ValueError):
                self.revise(patch=change)
            self.assertEqual(self.db.get("owner", self.event), before)
        with self.db.connect() as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM revisions").fetchone()[0], 0
            )

    def test_incompatible_model_update_cannot_invalidate_corrected_interval(
        self,
    ) -> None:
        self.revise(patch={"start": 50})
        with self.assertRaises(ValueError):
            self.propose(start=10, end=40)
        self.assertEqual(self.db.get("owner", self.event)["data"]["start"], 50)

    def test_owner_and_album_boundaries(self) -> None:
        self.db.add_album("other-owner", "album")
        self.assertEqual(self.db.list_events("other-owner", "album"), [])
        with self.assertRaises(KeyError):
            self.db.get("other-owner", self.event)
        with self.assertRaises(KeyError):
            self.db.create_event("owner", "different-album", "video", delivery())
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.add_asset("owner", "absent", "new", "video", 120, "fp")
        with self.db.connect() as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM assets WHERE id='new'").fetchone()[0],
                0,
            )

    def test_rediscovery_does_not_change_rule_or_original(self) -> None:
        self.db.add_album("owner", "album", "different-person")
        self.db.add_asset("owner", "album", "video", "video", 120, "original-v1")
        with self.db.connect() as db:
            self.assertEqual(
                db.execute("SELECT default_batter FROM albums").fetchone()[0],
                "person-a",
            )
        with self.assertRaises(Conflict):
            self.db.add_asset("owner", "album", "video", "video", 120, "replacement")

    def test_photo_has_activity_but_no_fake_video_interval(self) -> None:
        self.db.add_asset("owner", "album", "photo", "photo", None, "photo-v1")
        fields = delivery(
            outcome="unknown",
            start=None,
            end=None,
            delivery_start=None,
            outcome_end=None,
        )
        event = self.db.create_event("owner", "album", "photo", fields)
        self.assertEqual(self.db.get("owner", event)["data"]["role"], "batting")
        with self.assertRaises(ValueError):
            self.db.create_event("owner", "album", "photo", delivery())

    def test_backup_restore_contains_committed_wal_corrections(self) -> None:
        self.revise(patch={"outcome": "six"})
        saved = self.path.with_suffix(".backup")
        restored = self.path.with_suffix(".restored")
        backup(self.path, saved)
        restore(saved, restored)
        self.assertEqual(
            Ledger(restored).get("owner", self.event)["data"]["outcome"], "six"
        )
        self.assertEqual(saved.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(FileExistsError):
            restore(saved, restored)
        with self.assertRaises(FileNotFoundError):
            backup(self.path.with_suffix(".absent"), saved)

    def test_initial_migration_backs_up_existing_database_and_refuses_future_schema(
        self,
    ) -> None:
        old = self.path.with_suffix(".old")
        sqlite3.connect(old).close()
        Ledger(old)
        self.assertEqual(len(list(old.parent.glob(old.name + ".before-v1-*"))), 1)
        with closing(sqlite3.connect(old)) as db:
            db.execute("PRAGMA user_version=99")
        with self.assertRaises(ValueError):
            Ledger(old)
        with self.assertRaises(ValueError):
            restore(old, self.path.with_suffix(".future"))

    def test_invalid_actions_and_records(self) -> None:
        for kwargs in (
            {"action": "forget"},
            {"patch": {"unexpected": 1}},
            {"patch": []},
            {},
            {"action": "accept", "patch": {"outcome": "six"}},
            {"action": "undo"},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.revise(**kwargs)
        for kind, duration in (
            ("gif", 12),
            ("video", None),
            ("video", 0),
            ("photo", 12),
        ):
            with self.assertRaises(ValueError):
                self.db.add_asset("owner", "album", "bad", kind, duration, "v1")
        with self.assertRaises(ValueError):
            self.db.create_event("owner", "album", "video", {})
        with self.assertRaises(ValueError):
            self.db.add_album("", "album")

    def test_failed_backup_is_removed_and_invalid_restore_is_refused(self) -> None:
        destination = self.path.with_suffix(".failed")
        source, target = MagicMock(), MagicMock()
        target.execute.return_value.fetchone.return_value = ("corrupt page",)
        with (
            patch("cricket.ledger.sqlite3.connect", side_effect=[source, target]),
            self.assertRaises(ValueError),
        ):
            backup(self.path, destination)
        self.assertFalse(destination.exists())
        source.close.assert_called_once()
        target.close.assert_called_once()
        source.execute.return_value.fetchone.side_effect = [(1,), ("corrupt page",)]
        with (
            patch("cricket.ledger.sqlite3.connect", return_value=source),
            self.assertRaises(ValueError),
        ):
            restore(self.path, destination)
        self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
