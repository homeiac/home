"""CR2 importer regressions, including duplicate inputs racing Mac and RTX dispatch."""
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch

import duckdb
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE/'enrichers'), str(HERE/'adapters')]
import canon_raw
import gphotos
import media_summary
from summary_cache import SummaryCache


class CanonTests(unittest.TestCase):
    def test_old_and_new_partitions(self):
        self.assertEqual(gphotos.file_kind('camera.Cr2'), 'media')
        self.assertEqual(gphotos.file_kind('camera.CR2.json'), 'sidecar')
        view = (HERE/'knowledge.sql').read_text().split('CREATE OR REPLACE VIEW gphotos_files AS')[1].split(';')[0]
        with duckdb.connect() as db:
            db.execute("""CREATE TABLE files AS SELECT 'gphotos' AS source,'cam.CR2' AS path,
                       'other' AS kind,'cr2' AS ext""")
            self.assertEqual(db.execute(view).fetchone()[2], 'media')

    def test_bad_preview_uses_typed_original(self):
        with tempfile.TemporaryDirectory() as folder:
            original = Path(folder)/'image.CR2'
            Image.new('RGB',(200,100)).save(original,format='JPEG')
            with patch.object(canon_raw,'preview_bytes',return_value=b'unusable'):
                data,source = canon_raw.frame(original,'/data/thumbs/test')
            self.assertEqual(source,'original-jpeg')
            self.assertEqual(Image.open(BytesIO(data)).size,(200,100))

    def test_concurrent_copies_infer_once_and_restart_reuses(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            names = ('one.CR2','two.cr2')
            for name in names:
                Image.new('RGB',(20,20)).save(root/name,format='JPEG')
            args=SimpleNamespace(index=folder,model='test',enricher='e',extra={},api='ollama',num_ctx=4096,endpoint='local')
            def run(name,cache):
                row=dict(path=name,ext='cr2',size_bytes=(root/name).stat().st_size,
                         album=None, people=[], has_geo=False,taken_ts=None)
                return media_summary.summarize(row,folder,args,cache=cache)
            cachefile=str(root/'answers.sqlite')
            with patch.object(canon_raw,'lookup',return_value={}), patch.object(canon_raw,'match_catalog',return_value=None), \
                    patch.object(media_summary,'ask_model',return_value='{"summary":"A green field.","tags":[]}') as model:
                with SummaryCache(cachefile) as cache, ThreadPoolExecutor(max_workers=2) as pool:
                    results=list(pool.map(lambda n:run(n,cache), names))
                    self.assertEqual([r['status'] for r in results], ['ok','ok'])
                with SummaryCache(cachefile) as cache:
                    self.assertEqual(run(names[0],cache)['inference_backend'],'reuse')
                self.assertEqual(model.call_count,1)

    def test_album_copy_requires_identical_bytes_and_rechecks_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'album').mkdir()
            annual, album = root/'image.cr2', root/'album/image.cr2'
            annual.write_bytes(b'ABCD')
            album.write_bytes(b'ABCD')
            with duckdb.connect(str(root/'knowledge.duckdb')) as db:
                db.execute("""CREATE VIEW gphotos_media AS SELECT * FROM (VALUES
                    ('image.cr2',NULL,'image.cr2',4,'cr2'),('album/image.cr2','album','image.cr2',4,'cr2'))
                    AS t(path,album,name,size_bytes,ext)""")
                db.execute("CREATE VIEW gphotos_album_dup AS SELECT * FROM gphotos_media WHERE album IS NOT NULL")
            with SummaryCache(str(root/'hash.sqlite')) as cache:
                self.assertEqual(canon_raw.album_copies(folder,folder,cache),[dict(path='album/image.cr2',size_bytes=4)])
                album.write_bytes(b'WXYZ')
                self.assertEqual(canon_raw.album_copies(folder,folder,cache),[])

    def test_recovery_claim_is_exact_and_expires(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with duckdb.connect(str(root/'knowledge.duckdb')) as db:
                db.execute("""CREATE MACRO gphotos_to_summarize(e) AS TABLE
                    SELECT * FROM (VALUES ('held','cr2',5,2),('new','cr2',7,1)) t(path,ext,size_bytes,taken_ts)""")
            claim = root/'_caption_reservations.json'
            items = [dict(path='held',size_bytes=5),dict(path='new',size_bytes=6)]
            for expires,wanted in [(4102444800,['new']),(0,['held','new'])]:
                claim.write_text(json.dumps(dict(expires=expires,items=items)))
                self.assertEqual([r['path'] for r in media_summary.queue(folder,'e',3)],wanted)


if __name__=='__main__':
    unittest.main()
