"""Keep a memory-guarded server allocation out of production at every client concurrency."""

import sqlite3
import unittest

from decision import decide


class DecisionTest(unittest.TestCase):
    def test_pressure_excludes_otherwise_fastest_allocation(self):
        with sqlite3.connect(":memory:") as db:
            db.executescript("""
                CREATE TABLE mac_factorial_runs(block,slots,offered,valid,seconds,per_minute,
                    peak_rss_mib,peak_pressure,error,mean_gpu_percent);
                CREATE TABLE mac_factorial_items(slots,offered,seconds);
            """)
            for block in (1, 2):
                for slots, offered, elapsed in ((2, 2, 140), (8, 2, 100), (8, 8, 90)):
                    failed = (block, slots, offered) == (2, 8, 2)
                    valid = 18 if failed else 20
                    db.execute("INSERT INTO mac_factorial_runs VALUES (?,?,?,?,?,?,?,?,?,?)",
                               (block, slots, offered, valid, elapsed, 60 * valid / elapsed, 1000,
                                2 if failed else 1, "interrupted" if failed else None, 95))
                    db.executemany("INSERT INTO mac_factorial_items VALUES (?,?,?)",
                                   [(slots, offered, elapsed / valid)] * valid)
            result = decide(db)
            self.assertEqual(result["memory_guard_slots"], 8)
            self.assertEqual(result["selected"], {"slots": 2, "offered": 2})
            self.assertFalse(any(cell["eligible"] for cell in result["cells"] if cell["slots"] == 8))


if __name__ == "__main__":
    unittest.main()
