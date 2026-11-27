"""Inventory and identity assumptions use synthetic owner-scoped fixtures."""

import tempfile
import unittest
from pathlib import Path

from cricket.importer import import_album, role_event, select_album, select_person
from cricket.ledger import Ledger


class ImportTests(unittest.TestCase):
    def test_role_identity_rules(self) -> None:
        self.assertEqual(
            role_event(
                "batting", duration=12, default_batter="a", featured_batter=True
            )["actor"],
            "a",
        )
        self.assertIsNone(
            role_event("batting", duration=12, default_batter="a")["actor"]
        )
        self.assertIsNone(
            role_event(
                "bowling", duration=12, default_batter="a", identified_actor="a"
            )["actor"]
        )
        self.assertEqual(
            role_event(
                "bowling",
                duration=12,
                default_batter="a",
                identified_actor="b",
                confirmed_people={"b"},
            )["actor"],
            "b",
        )
        self.assertIsNone(
            role_event("other", duration=None, default_batter="a")["start"]
        )
        with self.assertRaises(ValueError):
            role_event("field", duration=12, default_batter="a")

    def test_resolve_unique_owned_album_and_person(self) -> None:
        album = {"name": "Cricket", "ownerMatches": True}
        self.assertEqual(select_album([album], "Cricket"), album)
        for albums in ([], [album, album], [{**album, "ownerMatches": False}]):
            with self.assertRaises(ValueError):
                select_album(albums, "Cricket")
        self.assertEqual(
            select_person([{"id": "a", "name": "Example Player"}], "Example"), "a"
        )
        self.assertEqual(
            select_person([{"id": "a", "name": "Example"}], "example"), "a"
        )
        with self.assertRaises(ValueError):
            select_person([], "Example")

    def test_import_is_resumable_and_dry_run_writes_nothing(self) -> None:
        asset = {
            "id": "v",
            "ownerId": "o",
            "type": "VIDEO",
            "duration": 12000,
            "exifInfo": {"fileSizeInByte": 10},
        }
        album = {"owner": "o", "id": "album", "assets": [asset]}
        sources = {"v": {"size": 10, "locator": "video.mp4", "fingerprint": "v1"}}
        self.assertEqual(import_album(None, album, sources, "a")["videos"], 1)
        with tempfile.TemporaryDirectory() as folder:
            ledger = Ledger(Path(folder) / "ledger")
            import_album(ledger, album, sources, "a")
            import_album(ledger, album, sources, "a")
            with ledger.connect() as db:
                self.assertEqual(
                    db.execute("SELECT count(*) FROM jobs").fetchone()[0], 1
                )
                self.assertEqual(
                    db.execute("SELECT duration FROM assets").fetchone()[0], 12
                )
        for changes, key in (
            ({"isOffline": True}, "unavailable"),
            ({"ownerId": "other"}, "out_of_scope"),
            ({"duration": 0}, "invalid_duration"),
        ):
            self.assertEqual(
                import_album(
                    None, {**album, "assets": [{**asset, **changes}]}, sources, "a"
                )[key],
                1,
            )
        self.assertEqual(import_album(None, album, {}, "a")["unavailable"], 1)
        with self.assertRaises(ValueError):
            import_album(None, {**album, "assets": [asset, asset]}, sources, "a")
        with self.assertRaises(ValueError):
            import_album(None, album, {"v": {**sources["v"], "size": 11}}, "a")
        photo = {**asset, "type": "IMAGE", "duration": None}
        self.assertEqual(
            import_album(None, {**album, "assets": [photo]}, sources, "a")["photos"], 1
        )


if __name__ == "__main__":
    unittest.main()
