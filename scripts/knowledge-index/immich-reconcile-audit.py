#!/usr/bin/env python3
"""Read-only source/Immich audit. Private details stay outside Git; stdout is counts."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import duckdb

HERE = Path(__file__).resolve().parent

def export(namespace, pod, user, database, query, target):
    sql = 'BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY; SET LOCAL statement_timeout=\'120s\'; SELECT row_to_json(q) FROM ('+query.strip().rstrip(';')+') q; COMMIT;'
    with target.open('w') as output:
        subprocess.run(['kubectl','--kubeconfig',os.environ.get('KUBECONFIG',str(Path.home()/'kubeconfig')),'-n',namespace,'exec','-i',pod,'--','psql','-XqAt','-v','ON_ERROR_STOP=1','-U',user,'-d',database],input=sql,text=True,stdout=output,check=True)

def audit(root):
    root.mkdir(mode=0o700,parents=True,exist_ok=True)
    export('database','postgres-postgresql-0','postgres','photo_enrichment',(HERE/'immich_sync/source.sql').read_text(),root/'source.jsonl')
    export('immich-pilot','deployment/immich-postgres','immich','immich',(HERE/'immich_sync/target-audit.sql').read_text(),root/'target.jsonl')
    with duckdb.connect() as db:
        db.execute('CREATE TABLE source AS SELECT * FROM read_json_auto(?)',[str(root/'source.jsonl')])
        db.execute('CREATE TABLE target AS SELECT *,replace(original_path,\'/external/gphotos/\',\'\') AS source_path FROM read_json_auto(?)',[str(root/'target.jsonl')])
        db.execute('''CREATE TABLE reconciliation AS SELECT s.path,t.id,t.original_path,s.summary,s.context_summary,s.size_bytes,
          CASE WHEN s.path IS NULL THEN 'target_only'
               WHEN NOT regexp_matches(s.path,'^Google Photos/Photos from [0-9]{4}/') THEN 'outside_import_scope'
               WHEN t.id IS NULL THEN 'missing_asset'
               WHEN count(t.id) OVER(PARTITION BY s.path)>1 THEN 'ambiguous_mapping'
               WHEN t.is_deleted OR t.is_offline THEN 'unavailable_asset'
               WHEN t.size_bytes IS DISTINCT FROM s.size_bytes THEN 'size_mismatch'
               ELSE 'matched' END AS disposition,
          length(coalesce(s.context_summary,s.summary,''))>0 AS has_summary,
          length(coalesce(t.description,''))>0 AS has_description,
          t.locked_properties
          FROM source s FULL OUTER JOIN target t ON t.is_external AND t.source_path=s.path''')
        counts=dict(db.execute('SELECT disposition,count(*) FROM reconciliation GROUP BY disposition ORDER BY disposition').fetchall())
        result={'captured_at':dt.datetime.now(dt.timezone.utc).isoformat(),'source_media':db.execute('SELECT count(*) FROM source').fetchone()[0],
          'source_successful_summaries':db.execute("SELECT count(*) FROM source WHERE length(coalesce(summary,''))>0").fetchone()[0],
          'source_context_summaries':db.execute("SELECT count(*) FROM source WHERE length(coalesce(context_summary,''))>0").fetchone()[0],
          'target_assets':db.execute('SELECT count(*) FROM target').fetchone()[0],
          'dispositions':counts,
          'matched_summary_available':db.execute("SELECT count(*) FROM reconciliation WHERE disposition='matched' AND has_summary").fetchone()[0],
          'matched_summary_with_existing_description':db.execute("SELECT count(*) FROM reconciliation WHERE disposition='matched' AND has_summary AND has_description").fetchone()[0],
          'checksum_algorithms':dict(db.execute('SELECT checksum_algorithm,count(*) FROM target GROUP BY 1').fetchall()),
          'identity_note':'Path and size join only. sha1-path is not a content checksum; verify source file identity before writes.'}
        db.execute('COPY reconciliation TO ? (FORMAT parquet)',[str(root/'reconciliation.parquet')])
        for table in ('source','target'):
            db.execute('COPY '+table+' TO ? (FORMAT parquet)',[str(root/(table+'.parquet'))])
        (root/'report.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2))

if __name__=='__main__':
    os.umask(0o077)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    audit(parser.parse_args().output)
