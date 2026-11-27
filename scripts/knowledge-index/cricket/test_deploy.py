"""A failed GUI rollout restores configuration without rolling back durable corrections."""

import base64
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cricket import host_deploy
from cricket.ledger import Ledger, backup
from cricket.test_ledger import delivery


class DeployTests(unittest.TestCase):
    def test_health_failure_restores_code_but_retains_existing_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            previous = root / "releases/old"
            previous.mkdir(parents=True)
            (previous / "venv").mkdir()
            (root / "gui").symlink_to(previous)
            unit = root / "gui.service"
            original = "[Service]\nExecStart=python serve\n"
            unit.write_text(original)
            state = root / "state"
            state.mkdir()
            ledger = Ledger(state / "ledger.sqlite3")
            ledger.add_album("o", "a", "p")
            ledger.add_asset("o", "a", "v", "video", 120, "v1")
            event = ledger.create_event("o", "a", "v", delivery(), manual=True)
            bootstrap = root / "bootstrap"
            backup(ledger.path, bootstrap)
            payload = {
                "previous": str(previous),
                "unit": original,
                "hashes": {},
                "release": "new",
                "files": {},
                "private": {
                    "ledger.sqlite3": base64.b64encode(bootstrap.read_bytes()).decode(),
                    "policy.json": base64.b64encode(
                        json.dumps({"enabled": False, "backends": {}}).encode()
                    ).decode(),
                },
            }
            with (
                patch.object(host_deploy, "ROOT", root),
                patch.object(host_deploy, "STATE", state),
                patch.object(host_deploy, "UNIT", unit),
                patch.object(host_deploy, "run"),
                patch("sys.stdin", io.StringIO(json.dumps(payload))),
                patch.object(
                    host_deploy.urllib.request,
                    "urlopen",
                    side_effect=OSError("fixture"),
                ),
                patch.object(host_deploy.time, "sleep"),
                self.assertRaises(RuntimeError),
            ):
                host_deploy.main()
            self.assertEqual((root / "gui").resolve(), previous)
            self.assertEqual(unit.read_text(), original)
            self.assertEqual(
                Ledger(state / "ledger.sqlite3").get("o", event)["data"], delivery()
            )
            self.assertTrue(list((root / "backups").glob("*/ledger.sqlite3")))


if __name__ == "__main__":
    unittest.main()
