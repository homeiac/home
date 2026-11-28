"""Operational retries cannot reset successful work or durable corrections."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cricket.ledger import Ledger
from cricket.ops import main, reanalyze, retry, status
from cricket.test_ledger import delivery
from cricket.worker import available_memory


class OpsTests(unittest.TestCase):
    def test_new_analysis_generation_preserves_completed_jobs_and_corrections(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = Ledger(root / "ledger")
            ledger.add_album("o", "a", "person-a")
            ledger.add_asset("o", "a", "v", "video", 120, "source")
            event = ledger.create_event(
                "o", "a", "v", delivery(outcome="attempted_run_out"), manual=True
            )
            with ledger.connect(True) as db:
                db.execute(
                    "INSERT INTO jobs(owner,asset,version,stage,state) VALUES('o','v','cricket-v1','analyze','complete')"
                )
            path = root / "policy.json"
            path.write_text(json.dumps({"enabled": True, "backends": {}}))
            self.assertEqual(reanalyze(ledger, path, "cricket-age-track-v1"), 1)
            self.assertEqual(reanalyze(ledger, path, "cricket-age-track-v1"), 0)
            self.assertEqual(
                json.loads(path.read_text())["analysis_version"], "cricket-age-track-v1"
            )
            self.assertEqual(
                ledger.get("o", event)["data"]["outcome"], "attempted_run_out"
            )
            with ledger.connect() as db:
                self.assertEqual(
                    db.execute(
                        "SELECT state FROM jobs WHERE version='cricket-v1'"
                    ).fetchone()[0],
                    "complete",
                )
            with self.assertRaises(ValueError):
                reanalyze(ledger, path, "cricket-v1")

    def test_retry_and_restore_are_scoped_and_nondestructive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = Ledger(root / "ledger")
            ledger.add_album("o", "a", "p")
            ledger.add_asset("o", "a", "v", "video", 120, "v1")
            event = ledger.create_event("o", "a", "v", delivery(), manual=True)
            with ledger.connect(True) as db:
                for version, state in [
                    ("v1", "error"),
                    ("v2", "complete"),
                    ("v3", "running"),
                ]:
                    db.execute(
                        "INSERT INTO jobs(owner,asset,version,stage,state) VALUES(?,?,?,?,?)",
                        ("o", "v", version, "analyze", state),
                    )
            self.assertEqual(retry(ledger, "v1"), 1)
            self.assertEqual(ledger.get("o", event)["data"]["outcome"], "four")
            self.assertEqual(
                {r["state"] for r in status(ledger)["jobs"]},
                {"queued", "complete", "running"},
            )
            with patch(
                "sys.argv",
                [
                    "ops",
                    "--ledger",
                    str(root / "ledger"),
                    "backup",
                    "--path",
                    str(root / "backup"),
                ],
            ):
                main()
            with patch(
                "sys.argv",
                [
                    "ops",
                    "--ledger",
                    str(root / "restored"),
                    "restore",
                    "--path",
                    str(root / "backup"),
                ],
            ):
                main()
            self.assertEqual(
                Ledger(root / "restored").get("o", event)["data"],
                ledger.get("o", event)["data"],
            )
            with (
                patch(
                    "sys.argv",
                    [
                        "ops",
                        "--ledger",
                        str(root / "ledger"),
                        "restore",
                        "--path",
                        str(root / "backup"),
                    ],
                ),
                self.assertRaises(FileExistsError),
            ):
                main()
            config = root / "policy"
            config.write_text(
                json.dumps(
                    {
                        "enabled": False,
                        "backends": {"mac": {"workers": 4, "max_workers": 4}},
                    }
                )
            )
            with patch(
                "sys.argv",
                [
                    "ops",
                    "--ledger",
                    str(root / "ledger"),
                    "--policy",
                    str(config),
                    "workers",
                    "--backend",
                    "mac",
                    "--workers",
                    "2",
                ],
            ):
                main()
            self.assertEqual(
                json.loads(config.read_text())["backends"]["mac"]["workers"], 2
            )

    def test_linux_pressure_reading(self) -> None:
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "pathlib.Path.read_text",
                return_value="MemTotal: 1000000 kB\nMemAvailable: 321 kB\n",
            ),
        ):
            self.assertEqual(available_memory(), 321 * 1024)
        with patch("pathlib.Path.exists", return_value=False):
            self.assertIsNone(available_memory())


if __name__ == "__main__":
    unittest.main()
