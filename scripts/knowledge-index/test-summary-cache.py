#!/usr/bin/env python3
"""Verify duplicate inference reuse without cross-context or error reuse."""
import copy
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).parent / "enrichers"))
from summary_cache import SummaryCache
import media_summary as media


class DuplicateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "cache.sqlite3")
        self.args = SimpleNamespace(enricher="e1", model="m", endpoint="http://fixture", api="ollama", num_ctx=8192, extra={})
        self.row = dict(path="one.jpg", size_bytes=3, ext="jpg", taken_ts=None, album=None, has_geo=False, people=[])

    def tearDown(self):
        self.tmp.cleanup()

    def test_renamed_copy_reuses_after_restart_and_preserves_path(self):
        with patch.object(media, 'jpeg_frame', return_value=b'jpg'), patch.object(media, 'ask_model', return_value='{"summary":"A dog.","tags":["dog"]}') as ask:
            with SummaryCache(self.path) as cache:
                first = media.summarize(self.row, self.tmp.name, self.args, cache=cache)
            # Simulate restart before the first Parquet batch committed.
            with SummaryCache(self.path) as cache:
                second = media.summarize(dict(self.row, path='album/copy.jpg'), self.tmp.name, self.args, cache=cache)
            self.assertEqual(ask.call_count, 1)
            self.assertEqual(first['summary'], second['summary'])
            self.assertEqual(second['path'], 'album/copy.jpg')
            self.assertEqual(second['status'], 'ok')

    def test_same_filename_and_size_different_pixels_do_not_reuse(self):
        with SummaryCache(self.path) as cache, patch.object(media, 'jpeg_frame', side_effect=[b'abc', b'def']), patch.object(media, 'ask_model', return_value='{"summary":"A dog."}') as ask:
            for _ in range(2): media.summarize(self.row, self.tmp.name, self.args, cache=cache)
            self.assertEqual(ask.call_count, 2)

    def test_context_model_and_options_remain_separate(self):
        with SummaryCache(self.path) as cache, patch.object(media, 'jpeg_frame', return_value=b'jpg'), patch.object(media, 'ask_model', return_value='{"summary":"A dog."}') as ask:
            media.summarize(self.row, self.tmp.name, self.args, cache=cache)
            media.summarize(dict(self.row, album='Holiday'), self.tmp.name, self.args, cache=cache)
            for name, value in [('model','another'),('enricher','e2'),('num_ctx',4096),('extra',{'think':False}),('api','openai')]:
                args=copy.copy(self.args); setattr(args,name,value)
                media.summarize(self.row, self.tmp.name, args, cache=cache)
            self.assertEqual(ask.call_count, 7)

    def test_errors_are_not_cached(self):
        with SummaryCache(self.path) as cache, patch.object(media, 'jpeg_frame', return_value=b'jpg'), patch.object(media, 'ask_model', side_effect=['invalid', '{"summary":"A dog."}']) as ask:
            self.assertEqual(media.summarize(self.row, self.tmp.name, self.args, cache=cache)['status'], 'error')
            self.assertEqual(media.summarize(self.row, self.tmp.name, self.args, cache=cache)['status'], 'ok')
            self.assertEqual(ask.call_count, 2)

    def test_hash_boundaries_and_frame_order(self):
        self.assertNotEqual(SummaryCache.key('x',[b'a',b'bc'],{}), SummaryCache.key('x',[b'ab',b'c'],{}))
        self.assertNotEqual(SummaryCache.key('x',[b'a',b'b'],{}), SummaryCache.key('x',[b'b',b'a'],{}))


if __name__ == '__main__': unittest.main()
