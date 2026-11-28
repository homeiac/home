"""Ensure an Immich readback distinguishes exact, independently filled and missing assets."""
import sqlite3
import unittest
from unittest.mock import patch

import audit


class ReadbackTest(unittest.TestCase):
    def test_counts_and_local_changes(self) -> None:
        with sqlite3.connect(':memory:') as db:
            db.executescript("""
                CREATE TABLE cohort(id TEXT PRIMARY KEY,cohort TEXT);
                CREATE TABLE work(id TEXT PRIMARY KEY,state TEXT,reason TEXT,answer TEXT);
                INSERT INTO cohort VALUES ('a','caption'),('b','caption'),('c','caption'),('d','caption'),('e','caption');
                INSERT INTO work VALUES ('a','queued',NULL,NULL),('b','error','competing',NULL),
                    ('c','verified',NULL,NULL),('d','queued',NULL,NULL);
            """)
            flags = {'a': [True, True, True, False], 'b': [True, False, True, False],
                     'c': [False, False, False, False], 'd': [True, False, False, True],
                     'e': [True, False, False, False]}
            with patch.object(audit, 'readback', return_value=flags):
                before = audit.audit(db, False)
                self.assertEqual(db.execute("SELECT state FROM work WHERE id='a'").fetchone()[0], 'queued')
                self.assertEqual(audit.audit(db, True), before)
                self.assertEqual(audit.audit(db, True), before)
            self.assertEqual(before, dict(cohort=5, asset_present=4, missing_caption=2, verified=1,
                                          already_described=2, owned_summary=2, visible_description=1))
            self.assertEqual(dict(db.execute('SELECT id,state FROM work')),
                             {'a':'verified','b':'already_described','c':'error','d':'already_described'})


if __name__ == '__main__':
    unittest.main()
