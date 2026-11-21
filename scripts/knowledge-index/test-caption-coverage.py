"""Regression test for combined counts across local and Luna Parquet datasets."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

import duckdb

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("export_metrics", HERE / "export-metrics.py")
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)


class CaptionCoverageTest(unittest.TestCase):
    def test_overlap_repeats_and_old_versions(self):
        with tempfile.TemporaryDirectory() as folder, duckdb.connect() as db:
            root = Path(folder)
            local = root / "summaries" / "worker"
            cloud = root / "luna"
            local.mkdir(parents=True)
            cloud.mkdir()
            db.execute("""CREATE TABLE gphotos_files AS SELECT * FROM (VALUES
                ('a',1,'media'),('a',1,'media'),('b',1,'media'),('c',1,'media'),('d',2,'media'),('e',3,'sidecar'))
                t(path,size_bytes,kind)""")
            db.execute("""COPY (SELECT path,size_bytes,'gphotos' AS source,'ok' AS status,
                timezone('UTC',current_timestamp)-age AS created_at FROM (VALUES
                ('a',1,INTERVAL '1 minute'),('a',1,INTERVAL '1 day'),('b',1,INTERVAL '2 minutes'),
                ('d',1,INTERVAL '1 minute')) t(path,size_bytes,age)) TO ?""", [str(local/"test.parquet")])
            db.execute("""COPY (SELECT source_path,size_bytes,state,timezone('UTC',current_timestamp) AS finished_at
                FROM (VALUES ('a',1,'ok'),('c',1,'ok'),('d',2,'error')) t(source_path,size_bytes,state)) TO ?""",
                       [str(cloud/"test.parquet")])
            out = exporter.Out()
            exporter.collect_coverage(out, db, str(root), str(cloud))
            self.assertEqual({labels["coverage"]: n for labels, n in out.rows["knowledge_index_caption_coverage"]},
                             dict(both=1, neither=1, local_only=1, luna_only=1))
            self.assertEqual(out.rows["knowledge_index_caption_first_saved_last_ten_minutes"], [({}, 2)])


if __name__ == "__main__":
    unittest.main()
