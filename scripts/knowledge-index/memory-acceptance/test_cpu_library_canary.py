"""Prevent duplicate or stale CPU writes while the original workers keep running."""

import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import cpu_library_canary as cpu
from library_backfill import claims, initialize


class CPUCanaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.db = sqlite3.connect(self.root / "library.sqlite3")
        self.addCleanup(self.db.close)
        initialize(self.db)
        cpu.initialize(self.db)
        with self.db:
            self.db.execute("INSERT INTO photos VALUES('p','x','2001','sum',0,'[]',0)")
            self.db.execute("""INSERT INTO jobs(asset,photo,day,input,status)
                VALUES('f','p','2001','{}','pending')""")

    def test_disabled_default_does_not_connect(self) -> None:
        self.assertEqual(cpu.run(argparse.Namespace(lanes=0)), {"enabled": False, "processed": 0})

    def test_claim_is_exclusive_and_finish_counts_once(self) -> None:
        asset, raw, generation = cpu.reserve(self.db, 60)
        with closing(sqlite3.connect(self.root / "library.sqlite3")) as other:
            self.assertIsNone(claims.claim(other, mac_batch=0, resume=False))
        cpu.checkpoint(self.db, asset, raw, generation, {"stage": "adult"})
        cpu.finish(self.db, asset, raw, generation, "complete", {"backend": "mac-cpu"})
        with self.assertRaises(cpu.ReservationLost):
            cpu.finish(self.db, asset, raw, generation, "complete", {})
        self.assertEqual(self.db.execute("SELECT status FROM jobs").fetchone()[0], "complete")

    def test_restart_reset_and_gpu_reclaim_fence_cpu(self) -> None:
        asset, raw, generation = cpu.reserve(self.db, 60)
        with self.db:
            self.db.execute("UPDATE jobs SET status='pending'")
            self.db.execute("DELETE FROM rtx_life_stage_claims")
        claims.claim(self.db, mac_batch=0, resume=False)
        with self.assertRaises(cpu.ReservationLost):
            cpu.checkpoint(self.db, asset, raw, generation, {"stage": "adult"})
        with self.assertRaises(cpu.ReservationLost):
            cpu.finish(self.db, asset, raw, generation, "complete", {})
        self.db.execute("UPDATE cpu_face_claims SET expires=0")
        self.db.commit()
        self.assertEqual(cpu.recover(self.db), 0)
        claims.finish(self.db, asset, "complete", "{}")

    def test_changed_input_rejects_output(self) -> None:
        asset, raw, generation = cpu.reserve(self.db, 60)
        with self.db:
            self.db.execute("UPDATE jobs SET input='changed'")
        with self.assertRaises(cpu.ReservationLost):
            cpu.finish(self.db, asset, raw, generation, "complete", {})

    def test_expired_generation_released_and_new_generation_wins(self) -> None:
        asset, raw, first = cpu.reserve(self.db, -1)
        self.assertEqual(cpu.recover(self.db), 1)
        _, _, second = cpu.reserve(self.db, 60)
        self.assertNotEqual(first, second)
        with self.assertRaises(cpu.ReservationLost):
            cpu.finish(self.db, asset, raw, first, "complete", {})
        cpu.finish(self.db, asset, raw, second, "complete", {})

    def test_failed_atomic_claim_hook_rolls_back(self) -> None:
        def fail(asset, raw):
            raise ValueError("failed metadata")
        with self.assertRaises(ValueError):
            claims.claim(self.db, mac_batch=0, resume=False, on_claim=fail)
        self.assertEqual(self.db.execute("SELECT status FROM jobs").fetchone()[0], "pending")
        self.assertEqual(self.db.execute("SELECT count(*) FROM rtx_life_stage_claims").fetchone()[0], 0)

    def test_lease_holder_and_expiry_are_enforced(self) -> None:
        from datetime import datetime, timezone
        renewed = datetime.now(timezone.utc).isoformat()
        answer = {"spec": {"holderIdentity": "owner", "renewTime": renewed, "leaseDurationSeconds": 60}}
        with patch.object(cpu.subprocess, "check_output", return_value=json.dumps(answer)):
            cpu.check_lease("pool", "owner")
            with self.assertRaises(cpu.PoolOwnershipLost):
                cpu.check_lease("pool", "other")
            answer["spec"]["leaseDurationSeconds"] = 0
        with patch.object(cpu.subprocess, "check_output", return_value=json.dumps(answer)):
            with self.assertRaises(cpu.PoolOwnershipLost):
                cpu.check_lease("pool", "owner")

    @patch.object(cpu, "check_lease")
    def test_bounded_adapter_reuses_infer_and_saves_cpu_attribution(self, lease):
        args = argparse.Namespace(lanes=1, root=self.root, backend="mac-cpu",
                                  endpoint="http://127.0.0.1:19480", model="cpu-model",
                                  profile="profile-v1", lease="pool", holder="owner",
                                  timeout=1, limit=1, joint=False, stop_file=None)
        def observed(row, backend, endpoint, saved, checkpoint, **kwargs):
            self.assertTrue(callable(kwargs["observer"]))
            checkpoint({"stage": "adult"})
            return "complete", {"stage": "adult", "action": "stands", "backend": backend}
        with patch.object(cpu, "infer", side_effect=observed):
            self.assertEqual(cpu.run(args)["states"], {"complete": 1})
        value = json.loads(self.db.execute("SELECT outcome FROM jobs").fetchone()[0])
        self.assertEqual(value["backend"], "mac-cpu")
        self.assertEqual(value["cpu_execution_profile"], "profile-v1")
        import importlib
        metrics = importlib.import_module("photo-stage-metrics")
        output = metrics.render(self.root / "library.sqlite3", self.root / "progress",
                                "library-face-observations")
        self.assertIn('backend="mac-cpu"} 1', output)
        self.assertNotIn('backend="mac-metal"} 1', output)


    @patch.object(cpu, "check_lease")
    def test_bad_response_has_bounded_retries_and_does_not_stall_queue(self, lease):
        args = argparse.Namespace(lanes=1, root=self.root, backend="mac-cpu",
                                  endpoint="http://127.0.0.1:19480", model="cpu-model",
                                  profile="profile-v1", lease="pool", holder="owner",
                                  timeout=1, limit=3, joint=False, stop_file=None)
        with patch.object(cpu, "infer", side_effect=ValueError("invalid response")):
            result = cpu.run(args)
        self.assertEqual(result["processed"], 2)
        self.assertEqual(self.db.execute("SELECT status,attempts FROM jobs").fetchone(), ("withheld", 2))

    @patch.object(cpu, "check_lease")
    def test_endpoint_failure_releases_job_without_marking_it_bad(self, lease) -> None:
        args = argparse.Namespace(lanes=1, root=self.root, backend="mac-cpu",
                                  endpoint="http://127.0.0.1:19480", model="cpu-model",
                                  profile="profile-v1", lease="pool", holder="owner",
                                  timeout=1, limit=3, joint=False, stop_file=None)
        with patch.object(cpu, "infer", side_effect=OSError("endpoint unavailable")):
            with self.assertRaises(OSError):
                cpu.run(args)
        self.assertEqual(self.db.execute("SELECT status,attempts FROM jobs").fetchone(), ("pending", 0))
        self.assertIsNotNone(claims.claim(self.db, mac_batch=0, resume=False))


if __name__ == "__main__":
    unittest.main()
