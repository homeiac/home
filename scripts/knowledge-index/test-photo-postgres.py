#!/usr/bin/env python3
"""Exercise migration, fencing, retries, live review and coherent snapshots."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from photo_enrichment.demo import build_demo
from photo_enrichment.faces import MODEL_ID
from photo_enrichment.store import Store
from photo_enrichment.worker import batch
from photo_enrichment.postgres import connect, migrate, PostgresStore
from photo_enrichment.snapshots import export_snapshot, analytical_connection


class EmptyFaces:
    def detect(self,path): return []


class FakeFaces:
    def detect(self,path):
        return [dict(id='stable-face',box=[.1,.1,.5,.5],confidence=.95,embedding=[1.,0.],model=MODEL_ID)]


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.index,self.library=build_demo(self.root)
        self.state=self.root/'state'
        with connect() as c:
            # This test runner supplies only an ephemeral loopback database.
            self.assertEqual(c.info.host,'127.0.0.1')
            c.execute('DROP SCHEMA public CASCADE; CREATE SCHEMA public; DROP SCHEMA IF EXISTS catalog CASCADE')
        legacy=Store(self.index,self.library,self.state)
        batch(legacy,FakeFaces(),1,'UTC')
        self.path=legacy.face('stable-face')['path']
        legacy.label_face('stable-face','Synthetic person')
        legacy.save_group(dict(paths=[self.path],event='Synthetic event'))
        batch(legacy,EmptyFaces(),2,'UTC')
        class Broken:
            def detect(self,path): raise ValueError('synthetic failure')
        batch(legacy,Broken(),1,'UTC')
        legacy.close()
        with connect() as c: self.counts=migrate(c,self.index,self.state)
        self.store=PostgresStore(self.index,self.library,self.state)

    def tearDown(self):
        self.store.close();self.temp.cleanup()

    def test_migration_preserves_results_and_rerun_is_idempotent(self):
        self.assertEqual(self.counts['face_scans'],3)
        self.assertEqual(self.counts['worker_attempts'],1)
        self.assertEqual(self.store.face('stable-face')['person'],'Synthetic person')
        self.assertEqual(self.store.groups()[0]['event'],'Synthetic event')
        with connect() as c:self.assertEqual(migrate(c,self.index,self.state),self.counts)
        self.assertEqual(self.store.seed_jobs(),5)
        self.assertEqual(self.store.queue_metrics()['ready'],5)
        selected=[]
        while job:=self.store.claim_job():
            selected.append(job['path'])
            self.assertTrue(self.store.process_job(job,EmptyFaces()))
        self.assertEqual(len(selected),4)  # imported retry remains backed off
        self.assertNotIn(self.path,selected)
        self.assertEqual(self.store.rows('SELECT count(*) n FROM face_scans')[0]['n'],7)

    def test_claim_fencing_and_atomic_completion(self):
        self.store.seed_jobs()
        job=self.store.claim_job()
        other=PostgresStore(self.index,self.library,self.state)
        try:
            second=other.claim_job()
            self.assertNotEqual(job['path'],second['path'])
            self.store.db.execute("UPDATE photo_jobs SET lease_until=now()-interval '1 second' WHERE path=?",[job['path']])
            self.assertFalse(self.store.process_job(job,EmptyFaces()))
            self.assertFalse(self.store.rows('SELECT * FROM face_scans WHERE path=?',[job['path']]))
            # Explicitly make this expired job next; reclaim creates a new fencing token.
            self.store.db.execute("UPDATE photo_jobs SET attempts=-1 WHERE path=?",[job['path']])
            new=other.claim_job()
            self.assertEqual(new['path'],job['path']);self.assertNotEqual(new['claim'],job['claim'])
            self.assertTrue(other.process_job(new,EmptyFaces()))
            self.assertFalse(self.store.process_job(job,FakeFaces()))
            self.assertEqual(self.store.rows('SELECT status FROM photo_jobs WHERE path=?',[job['path']])[0]['status'],'done')
        finally:other.close()

    def test_live_gui_reads_and_snapshot_retains_old_generation(self):
        first=export_snapshot(self.state)
        reader,manifest=analytical_connection(self.state)
        try:
            self.store.label_face('stable-face','Changed synthetic name')
            self.assertEqual(self.store.face_library(status='named')['people'][0]['person'],'Changed synthetic name')
            self.assertEqual(reader.execute("SELECT person FROM faces WHERE id='stable-face'").fetchone()[0],'Synthetic person')
            second=export_snapshot(self.state)
            self.assertNotEqual(first['generation'],second['generation'])
            self.assertEqual(reader.execute("SELECT person FROM faces WHERE id='stable-face'").fetchone()[0],'Synthetic person')
            fresh,_=analytical_connection(self.state)
            self.assertEqual(fresh.execute("SELECT person FROM faces WHERE id='stable-face'").fetchone()[0],'Changed synthetic name')
            fresh.close()
            before=(self.state/'analytics/current.json').read_bytes()
            with patch('photo_enrichment.snapshots.atomic_json',side_effect=OSError('synthetic disk failure')):
                with self.assertRaises(OSError):export_snapshot(self.state)
            self.assertEqual((self.state/'analytics/current.json').read_bytes(),before)
        finally:reader.close()

    def test_bulk_labels_reject_stale_revision_atomically(self):
        face=self.store.face_library(status='named')['faces'][0]
        self.store.label_face(face['id'],'Newer edit',str(face['revision']))
        with self.assertRaises(ValueError):
            self.store.label_faces([{'id':face['id'],'revision':str(face['revision'])}],'Stale edit')
        self.assertEqual(self.store.face(face['id'])['person'],'Newer edit')

    def test_snapshot_remains_consistent_during_concurrent_edit(self):
        import duckdb
        real_connect=duckdb.connect
        writer=PostgresStore(self.index,self.library,self.state)
        class ConcurrentConnection:
            def __init__(self):self.inner=real_connect();self.changed=False
            def __enter__(self):return self
            def __exit__(self,*args):self.inner.close()
            def execute(self,statement,*args):
                result=self.inner.execute(statement,*args)
                if statement.startswith('COPY source.public.extracted') and not self.changed:
                    writer.label_face('stable-face','Concurrent edit')
                    self.changed=True
                return result
        try:
            with patch('photo_enrichment.snapshots.duckdb.connect',side_effect=ConcurrentConnection):
                export_snapshot(self.state)
            reader,_=analytical_connection(self.state)
            try:self.assertEqual(reader.execute("SELECT person FROM faces WHERE id='stable-face'").fetchone()[0],'Synthetic person')
            finally:reader.close()
            self.assertEqual(writer.face('stable-face')['person'],'Concurrent edit')
        finally:writer.close()


if __name__=='__main__': unittest.main()
