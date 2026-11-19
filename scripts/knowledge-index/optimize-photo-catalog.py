#!/usr/bin/env python3
"""Inspect or refresh planner statistics for the photo catalog; never change labels."""
import argparse
import os
import shlex
import subprocess

REMOTE=r'''
import os,sys,json
from pathlib import Path
root=Path('/opt/photo-enrichment/gui').resolve()
sys.path.insert(0,str(root))
os.environ.update(PGSERVICEFILE='/etc/photo-enrichment/pg_service.conf',PGPASSFILE='/etc/photo-enrichment/pgpass')
from photo_enrichment.postgres import connect
from psycopg import sql
query="""SELECT f.id,f.path,f.box,f.confidence,f.person,f.label_source,f.updated_at AS revision,m.capture_ts,m.latitude,m.longitude,m.summary
 FROM faces f JOIN face_scans fs ON fs.path=f.path AND fs.size_bytes=f.size_bytes AND fs.mtime_ns=f.mtime_ns AND fs.model=f.model
 JOIN enriched_media m ON m.path=f.path AND m.size_bytes=f.size_bytes
 WHERE NOT EXISTS (SELECT 1 FROM catalog.gphotos_album_dup d WHERE d.path=f.path) AND f.person IS NULL
 ORDER BY m.capture_ts DESC NULLS LAST,f.id LIMIT 48 OFFSET 0"""
with connect() as c:
 c.execute("SET statement_timeout='10s'; SET lock_timeout='3s'")
 stats=c.execute("SELECT schemaname,relname,n_live_tup,last_analyze,last_autoanalyze FROM pg_stat_user_tables ORDER BY schemaname,relname").fetchall()
 print('planner_statistics:',json.dumps(stats,default=str))
 print('plan_before:', '\n'.join(row[0] for row in c.execute('EXPLAIN '+query)))
 if sys.argv[1]=='apply':
  for schema,table in [('catalog',name) for name in ('gphotos_media','gphotos_sidecars','gphotos_album_dup','media_summaries')]+[('public',name) for name in ('faces','face_scans','extracted')]:
   c.execute(sql.SQL('ANALYZE {}.{}').format(sql.Identifier(schema),sql.Identifier(table)))
  print('plan_after:', '\n'.join(row[0] for row in c.execute('EXPLAIN (ANALYZE,BUFFERS) '+query)))
'''

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10',os.environ['CB_HOST'],
        '/opt/photo-enrichment/gui/venv/bin/python -c '+shlex.quote(REMOTE)+' '+('apply' if args.apply else 'inspect')],check=True,timeout=90)
