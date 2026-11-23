"""Check copy reuse, version matching and model-specific completion counts."""
from pathlib import Path
import tempfile
import unittest

import duckdb
from caption_completion import completion_counts


class CompletionTest(unittest.TestCase):
    def test_copies_models_versions_and_repeated_results(self):
        with tempfile.TemporaryDirectory() as folder, duckdb.connect() as db:
            root = Path(folder)
            local = root / 'summaries/worker'
            cloud = root / 'luna'
            local.mkdir(parents=True)
            cloud.mkdir()
            db.execute("""CREATE TABLE gphotos_files AS SELECT * FROM (VALUES
                ('/Photos from 2020/a.jpg','a.jpg',10,'jpg','media'),
                ('/Photos from 2021/a.jpg','a.jpg',10,'jpg','media'),
                ('/Album/a.jpg','a.jpg',10,'jpg','media'),
                ('/Other/a.jpg','a.jpg',10,'jpg','media'),
                ('/Other/a.jpg','a.jpg',10,'jpg','media'),
                ('/Album/b.jpg','b.jpg',20,'jpg','media'),
                ('/Other/b.jpg','b.jpg',20,'jpg','media'),
                ('/Album/a-new.jpg','a.jpg',11,'jpg','media'),
                ('/Photos from 2020/v.mov','v.mov',30,'mov','media'),
                ('/Album/v.mov','v.mov',30,'mov','media'),
                ('/Album/a.json','a.json',3,'json','sidecar')
            ) t(path,name,size_bytes,ext,kind)""")
            # Caption only the album copy; repeat it to simulate multiple batches/models.
            db.execute("""COPY (SELECT * FROM (VALUES
                ('/Album/a.jpg',10,'gphotos','ok'),('/Album/a.jpg',10,'gphotos','ok'),
                ('/Album/b.jpg',19,'gphotos','ok'),('/Other/b.jpg',20,'gphotos','error'),
                ('/Photos from 2020/v.mov',30,'gphotos','ok')
            ) t(path,size_bytes,source,status)) TO ?""", [str(local/'saved.parquet')])
            db.execute("""COPY (SELECT * FROM (VALUES
                ('/Photos from 2020/a.jpg',10,'ok'),('/Album/b.jpg',20,'ok'),
                ('/Album/v.mov',30,'error')
            ) t(source_path,size_bytes,state)) TO ?""", [str(cloud/'saved.parquet')])
            rows = {(k,m,s): (total,done) for k,m,s,total,done in completion_counts(db,str(root),str(cloud))}
            self.assertEqual(rows['photo','local','deduplicated'], (5,1))
            self.assertEqual(rows['photo','local','including_copies'], (7,3))
            self.assertEqual(rows['photo','luna','deduplicated'], (5,2))
            self.assertEqual(rows['photo','luna','including_copies'], (7,4))
            self.assertEqual(rows['photo','either','deduplicated'], (5,2))
            self.assertEqual(rows['photo','either','including_copies'], (7,4))
            self.assertEqual(rows['video','local','deduplicated'], (1,1))
            self.assertEqual(rows['video','local','including_copies'], (2,2))
            self.assertEqual(rows['video','luna','including_copies'], (2,0))
            # No datasets means remaining work, never a fabricated completion.
            empty = completion_counts(db,str(root/'missing'),str(root/'missing'))
            self.assertTrue(all(done == 0 for _,_,_,_,done in empty))
            # A local-only installation must still report local coverage.
            only_local = completion_counts(db,str(root),str(root/'missing'))
            self.assertEqual(next(done for k,m,s,_,done in only_local
                                  if (k,m,s)==('photo','either','including_copies')),3)


if __name__ == '__main__':
    unittest.main()
