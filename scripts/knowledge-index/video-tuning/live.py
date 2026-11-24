#!/usr/bin/env python3
"""Read aggregate fresh production work since a tuning rollout, without media IDs."""
import argparse
import datetime
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time


def collect(since):
    import duckdb
    start=datetime.datetime.fromisoformat(since.replace('Z','+00:00'))
    if start.tzinfo is None:raise ValueError('Use an explicit timezone')
    epoch=start.timestamp();elapsed=time.time()-epoch
    base=Path('/local-3TB-backup/knowledge-index/summaries/gemma4-e2b-p1')
    files=[str(p) for p in base.glob('*.parquet') if p.stat().st_mtime>=epoch]
    if not files:return dict(since_utc=start.isoformat(),elapsed_seconds=round(elapsed),saved=0)
    with duckdb.connect(config={'threads':2}) as d:
        d.read_parquet(files,union_by_name=True).create_view('new_rows')
        d.execute("""CREATE TEMP TABLE fresh AS SELECT * FROM new_rows WHERE created_at>=?
            AND regexp_matches(lower(path),'[.](mp4|mov|3gp|avi|mpg|m4v)$')""",
            [start.astimezone(datetime.timezone.utc).replace(tzinfo=None)])
        rows=d.execute('''SELECT model,status,count(*),coalesce(sum(duration_s),0),
            min(frames_sampled),max(frames_sampled),list(DISTINCT prompt_version)
            FROM fresh GROUP BY model,status''').fetchall()
        total,unique,seconds=d.execute("""SELECT count(*),count(DISTINCT (source,path,size_bytes,enricher)),
            coalesce(sum(duration_s),0) FROM fresh WHERE status='ok'""").fetchone()
    return dict(since_utc=start.isoformat(),elapsed_seconds=round(elapsed),saved=total,unique_saved=unique,
        duplicate_successes=total-unique,clips_per_minute=round(total*60/elapsed,2),
        source_minutes_per_minute=round(seconds/elapsed,2),
        backends=[dict(model=m,status=s,rows=n,source_minutes=round(sec/60,2),frames_min=lo,frames_max=hi,
                       prompt_versions=versions) for m,s,n,sec,lo,hi,versions in rows])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--since',required=True)
    p.add_argument('--host')
    a=p.parse_args()
    if a.host:
        command='/opt/knowledge-index/venv/bin/python - --since '+shlex.quote(a.since)
        subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10',a.host,command],
                       input=Path(__file__).read_bytes(),check=True)
    else:print(json.dumps(collect(a.since)))

if __name__=='__main__':main()
