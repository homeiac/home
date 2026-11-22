#!/usr/bin/env python3
"""Verify the frozen recovery cohort and inspect the PNG backup without mutations."""
import hashlib
import json
from pathlib import Path
import subprocess

import duckdb

ROOT=Path('/local-3TB-backup')
items=json.loads(Path('/var/tmp/caption-gaps-20261122.json').read_text())
with duckdb.connect() as db:
    db.execute('SET threads=2')
    db.execute("CREATE TEMP TABLE results AS SELECT path,size_bytes,status FROM read_parquet(?,union_by_name=true)",
               [str(ROOT/'knowledge-index/summaries/*/*.parquet')])
    recovered=0;remaining=0
    for item in items:
        count=db.execute("SELECT count(*) FROM results WHERE path=? AND size_bytes=? AND status='ok'",
                         [item['path'],item['size_bytes']]).fetchone()[0]
        if count:recovered+=1
        else:remaining+=1
        print(json.dumps({'job_id':item['job_id'],'successful_local_rows':count,'resolved':bool(count)}))
    print(json.dumps({'recovered':recovered,'left_uncaptioned':remaining}))
copies=Path('/var/tmp/caption-gap-copies.json')
if copies.exists():
    for copy in json.loads(copies.read_text()):
        item=next(i for i in items if i['job_id']==copy['job_id'])
        with (ROOT/'gphotos/library'/item['path']).open('rb') as stream:
            digest=hashlib.file_digest(stream,'sha256').hexdigest()
        print(json.dumps({'job_id':item['job_id'],'backup_matches_original_sha256':digest==copy['sha256']}))
