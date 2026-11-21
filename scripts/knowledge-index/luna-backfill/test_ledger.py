"""Offline checks for cost reservations and atomic caption corrections."""
import importlib.util
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import duckdb


class LedgerTest(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("luna_host", Path(__file__).with_name("host.py"))
        self.host = importlib.util.module_from_spec(spec)
        modules = {name: MagicMock() for name in ("photo_enrichment", "photo_enrichment.snapshots",
                   "photo_enrichment.context_worker", "photo_enrichment.postgres", "media_summary")}
        with patch.dict(sys.modules, modules):
            spec.loader.exec_module(self.host)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.host.ROOT = Path(self.tmp.name)
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.db.executescript("""CREATE TABLE config(key TEXT PRIMARY KEY,value TEXT);
          INSERT INTO config VALUES ('pilot_cost','1000000');
          CREATE TABLE jobs(id INTEGER PRIMARY KEY,path TEXT,size_bytes INTEGER,ext TEXT,metadata TEXT,
              state TEXT DEFAULT 'pending',batch TEXT,cost INTEGER DEFAULT 0,result TEXT,started TEXT,
              finished TEXT,published INTEGER DEFAULT 0);
          INSERT INTO jobs(path,size_bytes,ext,metadata) VALUES ('a',12,'jpg','{"gps":{"latitude":2,"longitude":3}}');
          INSERT INTO jobs(path,size_bytes,ext,metadata) VALUES ('b',19,'jpg','{}');""")
        self.host.migrate(self.db)

    def claim(self, cap=250):
        return self.host.reserve(self.db, dict(estimated_limit_usd=cap,batch_size=12))

    def settle(self, grant, item, state='ok'):
        self.host.finish(self.db, dict(batch=grant['batch'],results=[dict(
            id=item['id'],state=state,input=10000,cached=4000,output=120,seconds=.1,
            summary='a saved caption',tags=['a'])]))

    def test_reservation_and_unknown(self):
        grant=self.claim(2)
        self.assertEqual(len(grant['items']),1)
        self.assertEqual(self.claim(2)['items'],[])
        self.settle(grant,grant['items'][0],'unknown')
        self.assertTrue(self.claim()['blocked'])
        self.assertEqual(self.db.execute('SELECT sum(cost) FROM jobs').fetchone()[0],1_000_000)

    def test_correction_replaces_same_file_and_keeps_cost(self):
        grant=self.claim()
        for item in grant['items']:
            self.settle(grant,item)
        self.host.publish(self.db)
        original=next((self.host.ROOT/'luna_codex_captions').glob('*.parquet'))
        correction=self.claim()
        self.assertEqual(len(correction['items']),1)
        self.assertEqual(self.db.execute('SELECT cost FROM previous_captions').fetchone()[0],700)
        self.assertEqual(self.host.publish(self.db)['published'],0)
        self.settle(correction,correction['items'][0])
        self.host.publish(self.db)
        self.assertEqual(list(original.parent.glob('*.parquet')),[original])
        self.assertEqual(duckdb.sql('SELECT count(*) FROM read_parquet(?)',params=[str(original)]).fetchone()[0],2)
        self.assertEqual(self.claim()['items'],[])


if __name__=='__main__':unittest.main()
