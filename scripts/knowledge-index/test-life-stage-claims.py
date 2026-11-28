"""Exercise RTX reservations against the existing Mac queue order."""

from pathlib import Path
import runpy
import sqlite3
import unittest


claims = runpy.run_path(str(Path(__file__).with_name("life-stage-claims.py")))


class LifeStageClaimsTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        with self.db:
            self.db.execute(
                "CREATE TABLE jobs(asset TEXT PRIMARY KEY, day TEXT, input TEXT, status TEXT, outcome TEXT)"
            )
            self.db.executemany("INSERT INTO jobs VALUES (?, 'same day', '{}', 'pending', NULL)",
                                [(f"asset-{i:02d}",) for i in range(40)])
            claims["initialize"](self.db)

    def test_resume_and_fallback(self):
        asset, _ = claims["claim"](self.db)
        self.assertEqual(asset, "asset-39")
        self.assertEqual(claims["claim"](self.db)[0], asset)
        claims["finish"](self.db, asset, "pending", None)
        self.assertEqual(claims["claim"](self.db)[0], "asset-38")

    def test_tail_exhaustion_never_reaches_mac_head(self):
        with self.db:
            self.db.execute(
                "INSERT INTO rtx_life_stage_claims SELECT asset, 'released' "
                "FROM jobs WHERE asset >= 'asset-16'"
            )
        self.assertIsNone(claims["claim"](self.db))

    def test_parallel_requests_have_distinct_reservations(self):
        first = claims["claim"](self.db, resume=False)
        second = claims["claim"](self.db, resume=False)
        self.assertNotEqual(first[0], second[0])
        self.assertCountEqual(claims["active"](self.db), [first, second])
        claims["finish"](self.db, second[0], "complete", "{}")
        self.assertEqual(claims["active"](self.db), [first])


if __name__ == "__main__":
    unittest.main()
