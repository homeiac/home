#!/usr/bin/env python3
"""Check durable worker resumption, retry fairness and Parquet recovery."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from photo_enrichment.demo import build_demo
from photo_enrichment.metrics import Metrics
from photo_enrichment.store import Store
from photo_enrichment.worker import batch, pending, run


class EmptyFaces:
    def detect(self, path):
        return []


class WorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.index, cls.library = build_demo(cls.root)
        cls.original = hashlib.sha256((cls.index / 'knowledge.duckdb').read_bytes()).hexdigest()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.state = Path(tempfile.mkdtemp(dir=self.root))
        self.store = Store(self.index, self.library, self.state)

    def tearDown(self):
        self.store.close()
        self.assertEqual(hashlib.sha256((self.index / 'knowledge.duckdb').read_bytes()).hexdigest(), self.original)

    def test_resume_and_zero_face_completion(self):
        self.assertEqual(batch(self.store, EmptyFaces(), 3, 'UTC')['selected'], 3)
        self.store.close()
        self.store = Store(self.index, self.library, self.state)
        self.assertEqual(batch(self.store, EmptyFaces(), 100, 'UTC')['selected'], 5)
        self.assertEqual(batch(self.store, EmptyFaces(), 100, 'UTC')['selected'], 0)
        self.assertEqual(self.store.rows('SELECT count(*) n FROM face_scans')[0]['n'], 8)
        self.assertEqual(self.store.rows('SELECT count(*) n FROM faces')[0]['n'], 0)
        self.assertEqual(self.store.rows("SELECT count(*) n FROM read_parquet(?)",
                         [str(self.state/'parquet/extracted.parquet')])[0]['n'], 8)

    def test_failure_backoff_does_not_starve_other_photos(self):
        class Broken:
            def detect(self, path):
                raise ValueError('synthetic model failure')
        first = batch(self.store, Broken(), 1, 'UTC', retry_seconds=60, now=100)
        self.assertEqual(first['errors'], 1)
        failed = self.store.rows('SELECT path FROM worker_attempts')[0]['path']
        self.assertNotIn(failed, [r['path'] for r in pending(self.store, 100, 'UTC', True, 101)])
        self.assertEqual(batch(self.store, EmptyFaces(), 100, 'UTC', now=101)['selected'], 7)
        self.assertEqual(batch(self.store, EmptyFaces(), 100, 'UTC', now=159)['selected'], 0)
        self.assertEqual(batch(self.store, EmptyFaces(), 100, 'UTC', now=161)['selected'], 1)
        self.assertEqual(self.store.rows('SELECT count(*) n FROM worker_attempts')[0]['n'], 0)

    def test_idle_repairs_export_after_commit(self):
        paths = [r['path'] for r in pending(self.store, 100, 'UTC', False, 0)]
        self.store.extract(paths, 'UTC')
        self.assertFalse((self.state/'parquet/extracted.parquet').exists())
        self.assertEqual(batch(self.store, None, 100, 'UTC')['selected'], 0)
        self.assertTrue((self.state/'parquet/extracted.parquet').exists())
        # Metadata-only processing must not incorrectly complete the face queue.
        self.assertEqual(len(pending(self.store, 100, 'UTC', True, 0)), 8)

    def test_batch_lookup_preserves_source_identity_checks(self):
        paths = [r['path'] for r in pending(self.store, 2, 'UTC', False, 0)]
        with patch.object(self.store, 'photo', side_effect=AssertionError('per-photo catalog lookup')):
            self.assertEqual(self.store.extract(paths, 'UTC')['processed'], 2)
        changed = self.state/'changed.jpg'
        changed.write_bytes(b'changed source')
        with patch('photo_enrichment.store.contained', return_value=changed):
            result = self.store.extract(paths[:1], 'UTC')
        self.assertEqual(result['processed'], 0)
        self.assertEqual(len(result['errors']), 1)
        self.assertIn('changed since indexing', result['errors'][0]['error'])

    def test_bounded_worker_publishes_terminal_telemetry(self):
        self.store.close()
        prom = self.state/'worker.prom'
        with Metrics(prom) as metrics:
            run(self.index, self.library, self.state, self.state/'models', metrics,
                batch_size=2, faces=False, pause_seconds=0, max_batches=2)
        self.store = Store(self.index, self.library, self.state)
        self.assertEqual(self.store.rows('SELECT count(*) n FROM extracted')[0]['n'], 4)
        self.assertIn('photo_enrichment_running 0', prom.read_text())
        self.assertIn('photo_enrichment_worker_stage 8', prom.read_text())


if __name__ == '__main__':
    unittest.main()
