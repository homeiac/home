#!/usr/bin/env python3
"""Read-only grouping benchmark on saved embeddings; outputs aggregate counts only."""
import json
import os
from pathlib import Path
import shlex
import subprocess

REMOTE = r'''
import json, os, time
os.environ.update(PGSERVICEFILE='/etc/photo-enrichment/pg_service.conf',PGPASSFILE='/etc/photo-enrichment/pgpass',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
import psycopg
from psycopg.rows import dict_row
payload=json.load(__import__('sys').stdin)
module={};exec(compile(payload['matching'],'matching.py','exec'),module)
groups={value:module['ReviewGroups'](value) for value in (.8,.65,.55)}
start=time.monotonic();count=0
with psycopg.connect(service='photo_pipeline',row_factory=dict_row) as connection:
 connection.execute('SET TRANSACTION READ ONLY')
 with connection.cursor(name='review_group_benchmark') as cursor:
  cursor.execute("""SELECT f.id,f.person,f.model,f.embedding FROM faces f
   JOIN face_scans fs ON fs.path=f.path AND fs.size_bytes=f.size_bytes AND fs.mtime_ns=f.mtime_ns AND fs.model=f.model
   WHERE f.person IS NULL AND EXISTS(SELECT 1 FROM catalog.gphotos_media m WHERE m.path=f.path AND m.size_bytes=f.size_bytes)
   AND NOT EXISTS(SELECT 1 FROM catalog.gphotos_album_dup d WHERE d.path=f.path) ORDER BY f.id""")
  while rows:=cursor.fetchmany(256):
   details={row['id']:dict(qualified=False) for row in rows}
   for grouper in groups.values():grouper.add(rows,details)
   count+=len(rows)
   if count%10240==0:print(json.dumps(dict(processed=count,seconds=round(time.monotonic()-start,1))),flush=True)
print(json.dumps(dict(detections=count,seconds=round(time.monotonic()-start,1),groups={str(k):len(v.groups) for k,v in groups.items()},repeated={str(k):sum(len(m)>1 for m in v.groups.values()) for k,v in groups.items()},ungrouped={str(k):sum(len(m)==1 for m in v.groups.values()) for k,v in groups.items()},retained={str(k):sum(map(len,v.groups.values())) for k,v in groups.items()})),flush=True)
'''
source=Path(__file__).parent/'photo_enrichment/matching.py'
subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10',os.environ['CB_HOST'],
                'nice -n 19 /opt/photo-enrichment/gui/venv/bin/python -c '+shlex.quote(REMOTE)],
               input=json.dumps(dict(matching=source.read_text())),text=True,check=True)
