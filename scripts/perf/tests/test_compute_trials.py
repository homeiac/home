"""Check the resource combinations that a route-only inventory would miss."""

import json
import runpy
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

planner = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "plan-compute-trials.py")
)


class ComputeTrialsTest(unittest.TestCase):
    def test_another_workload_plugs_in_without_engine_changes(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            sample = dict(
                pending=25,
                healthy=True,
                room={"embed/cpu": 2, "embed/gpu": 1},
                safe={"embed/cpu": True, "embed/gpu": True},
            )
            (root / "embed.py").write_text("print(" + repr(json.dumps(sample)) + ")")
            policy = root / "policy.json"
            policy.write_text(
                json.dumps(
                    {"feedback_adapter": "embed.py", "feedback": {"min_pending": 4}}
                )
            )
            driver = Path(__file__).resolve().parents[1] / "plan-compute-trials.py"
            result = json.loads(
                subprocess.check_output([sys.executable, str(driver), str(policy)])
            )
            self.assertEqual(result["next_pool"], "embed/cpu")

    def test_independent_host_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            inventory = Path(folder) / "inventory"
            inventory.write_text(
                "[proxmox]\n192.0.2.1 # new-host\n[guests]\n192.0.2.2 # guest\n"
            )
            self.assertEqual(planner["host_cpus"](inventory), {"new-host/cpu"})

    def test_every_stage_and_device_has_its_own_evidence(self) -> None:
        record = {
            "profile": "v1",
            "review_on": "2030-01-01",
            "state": "baseline",
            "reason": "observed",
        }
        policy = {
            "stages": {
                "decode": {"profile": "v1", "evidence": {"mac/metal": record}},
                "infer": {"profile": "v2", "evidence": {"mac/metal": record}},
            }
        }
        pools = {"mac/metal", "mac/cpu"}
        rows = planner["plan"](policy, pools, date(2026, 11, 27))
        self.assertEqual(
            {(s, p): a for s, p, a, _ in rows},
            {
                ("decode", "mac/metal"): "TUNE BASELINE",
                ("infer", "mac/metal"): "REASSESS",
                ("decode", "mac/cpu"): "PREFLIGHT + CANARY",
                ("infer", "mac/cpu"): "PREFLIGHT + CANARY",
            },
        )
        expired = planner["plan"](policy, pools, date(2030, 1, 1))
        self.assertIn(("decode", "mac/metal", "REASSESS", "observed"), expired)


if __name__ == "__main__":
    unittest.main()
