#!/usr/bin/env python3
"""Audit current audio/story output for uniqueness, progress and snapshot freshness."""
import argparse,json,sqlite3,subprocess,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--host');a=p.parse_args()
if a.host:
 subprocess.run(['ssh',a.host,'/opt/knowledge-index/venv/bin/python -'],input=Path(__file__).read_bytes(),check=True);raise SystemExit
root=Path('/local-3TB-backup/photo-enrichment/audio-story')
with sqlite3.connect('file:'+str(root/'ledger.sqlite3')+'?mode=ro',uri=True) as d:
 r={'checked_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
    'ledger_rows':d.execute('SELECT count(*) FROM jobs WHERE active=1').fetchone()[0],
    'audio_states':dict(d.execute('SELECT audio_state,count(*) FROM jobs WHERE active=1 GROUP BY 1')),
    'story_states':dict(d.execute('SELECT story_state,count(*) FROM jobs WHERE active=1 GROUP BY 1')),
    'visual_sources':dict(d.execute('SELECT visual_source,count(*) FROM jobs WHERE active=1 GROUP BY 1')),
    'audio_repeated_successes':d.execute("SELECT count(*) FROM (SELECT job FROM attempts WHERE stage='audio' AND ok=1 GROUP BY job HAVING count(*)>1)").fetchone()[0],
    'unpublished_updates':d.execute('SELECT count(*) FROM jobs WHERE active=1 AND updated>coalesce(published,0)').fetchone()[0],
    'stages':dict(d.execute('SELECT stage,count(*) FROM attempts GROUP BY stage'))}
 snapshot=root/'parquet/current.parquet'
 if snapshot.exists():
  import duckdb
  with duckdb.connect(config={'threads':1}) as q:
   rows,unique=q.execute('SELECT count(*),count(DISTINCT (path,size_bytes,version)) FROM read_parquet(?)',[str(snapshot)]).fetchone()
   r.update(snapshot_rows=rows,snapshot_unique_items=unique,snapshot_duplicates=rows-unique,snapshot_age_seconds=round(time.time()-snapshot.stat().st_mtime,1))
print(json.dumps(r))
