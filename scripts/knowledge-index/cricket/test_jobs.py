"""Lease ownership, restart recovery, and cached window checkpoints."""

import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from cricket.jobs import claim, failed, heartbeat
from cricket.ledger import Conflict, Ledger
from cricket.prepare import save_private
from cricket.reconcile import reconcile
from cricket.test_reconcile import observation
from cricket.worker import export, policy, process


class JobTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ledger = Ledger(self.root / "ledger")
        self.ledger.add_album("o", "a", "person-a")
        self.ledger.add_asset("o", "a", "v", "video", 120, "v1")
        with self.ledger.connect(True) as db:
            db.execute(
                "INSERT INTO jobs(owner,asset,version,stage) VALUES('o','v','v1','analyze')"
            )
        save_private(
            self.root / "evidence/v.json",
            {"asset": "v", "cache_key": "source-v1", "windows": [{}, {}]},
        )

    def claim(self, now: float = 100) -> dict | None:
        return claim(self.ledger, "o", "a", "v1", self.root / "evidence", now)

    def test_pilot_scope_leaves_other_work_queued(self) -> None:
        self.assertIsNone(
            claim(
                self.ledger, "o", "a", "v1", self.root / "evidence", 100, allowed=set()
            )
        )
        with self.ledger.connect() as db:
            self.assertEqual(
                db.execute("SELECT state FROM jobs").fetchone()[0], "queued"
            )
        self.assertEqual(
            claim(
                self.ledger, "o", "a", "v1", self.root / "evidence", 100, allowed={"v"}
            )["asset"],
            "v",
        )

    def test_only_one_dispatcher_can_claim_a_job_and_stale_workers_are_fenced(
        self,
    ) -> None:
        with ThreadPoolExecutor(2) as pool:
            jobs = list(pool.map(lambda _: self.claim(), range(2)))
        first = next(j for j in jobs if j is not None)
        self.assertEqual(sum(j is not None for j in jobs), 1)
        second = self.claim(1100)
        self.assertNotEqual(first["lease"], second["lease"])
        with self.assertRaises(Conflict):
            heartbeat(self.ledger, first, 1)
        with self.assertRaises(Conflict):
            reconcile(
                self.ledger,
                "o",
                "a",
                "v",
                "v1",
                [observation()],
                model="fixture",
                version="v1",
                run="r",
                lease=first["lease"],
            )
        self.assertEqual(self.ledger.list_events("o", "a"), [])

    def test_failed_assets_keep_checkpoints_and_stop_after_three_attempts(self) -> None:
        for n in range(3):
            job = self.claim(10**12 + n * 1000)
            heartbeat(self.ledger, job, 1)
            failed(self.ledger, job, "fixture failure")
        self.assertIsNone(self.claim(10**13))
        with self.ledger.connect() as db:
            row = db.execute("SELECT * FROM jobs").fetchone()
            self.assertEqual(row["state"], "error")
            self.assertEqual(row["attempts"], 3)
            self.assertEqual(json.loads(row["checkpoint"])["completed_windows"], 1)

    def test_successful_windows_survive_retry_and_completion_is_atomic(self) -> None:
        job = self.claim()
        backend = {"model": "fixture", "api": "openai"}
        with (
            patch(
                "cricket.worker.analyze_one",
                side_effect=[{"proposals": [observation()]}, ValueError("failure")],
            ),
            self.assertRaises(ValueError),
        ):
            process(
                self.ledger,
                {"id": "a", "default_batter": "person-a"},
                job,
                backend,
                self.root / "evidence",
                self.root,
                None,
            )
        with patch(
            "cricket.worker.analyze_one", return_value={"proposals": [observation(31)]}
        ) as infer:
            process(
                self.ledger,
                {"id": "a", "default_batter": "person-a"},
                job,
                backend,
                self.root / "evidence",
                self.root,
                None,
            )
            self.assertEqual(infer.call_count, 1)
        with self.ledger.connect() as db:
            self.assertEqual(
                db.execute("SELECT state FROM jobs").fetchone()[0], "complete"
            )
        self.assertEqual(len(self.ledger.list_events("o", "a")), 1)
        export(self.ledger, self.root / "effective")
        self.assertEqual(
            len(json.loads((self.root / "effective/a.json").read_text())["events"]), 1
        )

    def test_jobs_without_prepared_evidence_wait_and_policy_bounds_are_enforced(
        self,
    ) -> None:
        self.assertIsNone(claim(self.ledger, "o", "a", "v1", self.root / "absent", 100))
        path = self.root / "policy.json"
        value = {"enabled": True, "backends": {"mac": {"workers": 4, "max_workers": 4}}}
        save_private(path, value)
        self.assertEqual(policy(path), value)
        for bad in (
            {"enabled": 1, "backends": {}},
            {"enabled": True, "backends": []},
            {"enabled": True, "backends": {"mac": {"workers": 5, "max_workers": 4}}},
        ):
            save_private(path, bad)
            with self.assertRaises(ValueError):
                policy(path)


if __name__ == "__main__":
    unittest.main()
