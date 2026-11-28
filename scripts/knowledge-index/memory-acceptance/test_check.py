"""Synthetic contract tests. No private library or service access."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import check


def write(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


class AcceptanceTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.baseline = self.directory / "baseline.json"

    def seed(self, journey="growing-up", **metadata):
        plan = check.template(journey)
        plan.update(dict.fromkeys(check.META, "fixture-v1"))
        plan.update(metadata)
        source = self.directory / "synthetic.txt"
        source.write_text("synthetic source for checker tests", encoding="utf-8")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        ledger = {"asset-1": {"state": "complete"}}
        answers = {"rows": ["asset-1"], "sequence": ["asset-1"], "text": "fixture-v1",
                   "names": {"asset-1": ["A", "Ren"]}, "deadline": 300, "ledger": ledger, "attempt_limit": 3}
        measurements = {**answers, "names": {"asset-1": "Ren smiles beside A."},
                        "deadline": 12, "zero": 0, "same_id": ["album-A", "album-A"],
                        "empty": [], "private": "private"}
        window = dict(start=1, end=2, items_per_minute=60, p95_seconds=0.5,
                      errors=0, retries=0, duplicates=0)
        measurements["tuning"] = dict(
            dashboard_panel="/d/knowledge-index/knowledge-index?viewPanel=900",
            scope="fixture", workload="same fixture input rate", bottleneck_evidence="timing capture",
            quality_evidence="reference comparisons", deployed_revision=plan["release"],
            decision_evidence="comparison across both windows", live_readback=True,
            decision="retained", queue_observed=False, queue_not_applicable="synchronous request",
            baseline=window, verification={**window, "start": 3, "end": 4},
        )
        captures = {}
        for task, rules in check.fields(journey).items():
            captures[task] = {"run_id": "test", "artifacts": {source.name: digest}, "observed": {}}
            for key, op in rules.items():
                if op in answers:
                    plan["expected"][task][key] = answers[op]
                captures[task]["observed"][key] = measurements[op]
        write(self.baseline, plan)
        for task, capture in captures.items():
            capture["baseline_sha256"] = hashlib.sha256(self.baseline.read_bytes()).hexdigest()
            write(self.directory / (task + ".json"), capture)

    def result(self):
        return check.evaluate(self.baseline, self.directory, "test")

    def modify(self, task, **changes):
        path = self.directory / (task + ".json")
        capture = check.load_object(path)
        capture["observed"].update(changes)
        write(path, capture)

    def test_three_synthetic_journeys(self):
        for journey in check.JOURNEYS:
            with self.subTest(journey=journey):
                self.seed(journey)
                self.assertEqual((self.result()["status"], self.result()["mode"]), ("PASS", "synthetic"))

    def test_platform_requires_three_live_rollouts_at_one_release(self):
        root = self.directory
        for journey in check.JOURNEYS:
            self.directory = root / journey
            self.directory.mkdir()
            self.baseline = self.directory / "baseline.json"
            self.seed(journey, mode="live", scope="rollout")
        self.assertEqual(check.platform(root, "test")["status"], "PASS")
        self.seed(journey, mode="live", scope="rollout", release="changed")
        self.assertEqual(check.platform(root, "test")["status"], "BLOCKED")
        self.seed(journey, mode="live", scope="reference")
        self.assertEqual(check.platform(root, "test")["status"], "BLOCKED")
        self.seed(journey, mode="synthetic", scope="rollout")
        self.assertEqual(check.platform(root, "test")["status"], "BLOCKED")

    def test_names_checked_on_displayed_text_not_substrings(self):
        self.seed()
        self.modify("context", displayed_primary_captions={"asset-1": "A stranger saw a wren."})
        report = self.result()
        self.assertEqual(report["tasks"]["context"]["failed"], ["displayed_primary_captions"])
        self.assertEqual(report["tasks"]["delivery"]["status"], "BLOCKED")
        self.assertEqual(report["tasks"]["identity"]["status"], "PASS")

    def test_correct_names_wrong_actions(self):
        self.seed()
        self.modify("context", reviewed_person_action_rows=["other assignment"])
        self.assertEqual(self.result()["status"], "FAIL")

    def test_tuning_required_even_when_product_observations_pass(self):
        self.seed()
        for task in check.fields("growing-up"):
            self.assertIn("grafana_live_tuning", check.fields("growing-up")[task])
        path = self.directory / "identity.json"
        capture = check.load_object(path)
        evidence = capture["observed"].pop("grafana_live_tuning")
        write(path, capture)
        self.assertEqual(self.result()["tasks"]["identity"]["status"], "BLOCKED")
        evidence["verification"]["duplicates"] = 1
        self.modify("identity", grafana_live_tuning=evidence)
        self.assertEqual(self.result()["tasks"]["identity"]["failed"], ["grafana_live_tuning"])
        evidence["verification"]["duplicates"] = 0
        evidence["deployed_revision"] = "different revision"
        self.modify("identity", grafana_live_tuning=evidence)
        self.assertEqual(self.result()["tasks"]["identity"]["failed"], ["grafana_live_tuning"])

    def test_missing_or_stale_evidence(self):
        self.seed()
        (self.directory / "retrieval.json").unlink()
        self.assertEqual(self.result()["status"], "BLOCKED")
        self.assertEqual(check.evaluate(self.baseline, self.directory, "other")["tasks"]["identity"]["status"], "BLOCKED")
        (self.directory / "synthetic.txt").write_text("changed")
        self.assertEqual(self.result()["tasks"]["identity"]["status"], "BLOCKED")

    def test_duplicates_exceptions_and_deadline(self):
        self.seed()
        self.modify("delivery", opened_album_assets=["asset-1", "asset-1"])
        self.modify("corrections", convergence_seconds=301)
        self.modify("accounting", asset_dispositions={"asset-1": {"state": "complete"},
                                                     "asset-2": {"state": "pending"}})
        report = self.result()
        for task in ("delivery", "corrections", "accounting"):
            self.assertEqual(report["tasks"][task]["status"], "FAIL")
        self.assertFalse(check.valid_oracle("ledger", {"asset-1": {"state": "accepted_exception"}}))

    def test_missing_oracle_and_inconsistent_oracle(self):
        self.seed()
        plan = check.load_object(self.baseline)
        plan["expected"]["identity"]["alias_query_matches"] = []
        write(self.baseline, plan)
        identity = self.directory / "identity.json"
        capture = check.load_object(identity)
        capture["baseline_sha256"] = hashlib.sha256(self.baseline.read_bytes()).hexdigest()
        write(identity, capture)
        self.assertIn("missing oracle alias_query_matches", self.result()["tasks"]["identity"]["missing"])
        plan["expected"]["delivery"]["opened_album_assets"] = ["different"]
        write(self.baseline, plan)
        with self.assertRaises(ValueError):
            self.result()


if __name__ == "__main__":
    unittest.main()
