#!/usr/bin/env python3
"""Read existing Knowledge Index descriptions and audit dog-priority coverage.

Read-only query; private descriptions/asset IDs are saved locally, only counts print.
"""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re
import subprocess
from distributed import KUBE

p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);args=p.parse_args()
os.umask(0o077);args.directory.mkdir(parents=True,exist_ok=True)
sql="""BEGIN READ ONLY; SET LOCAL statement_timeout='30s';
SELECT jsonb_build_object('kind','job','asset_id',asset_id,'status',status,'ordinal',ordinal,'matched',coalesce(jsonb_array_length(result->'matches'),0)>0)
 FROM waffles.jobs WHERE run_id='historical-waffles';
SELECT jsonb_build_object('kind','description','asset_id',asset_id,'description',
 coalesce(applied->>'summary',payload->>'summary','') || ' ' || coalesce((applied->'tags')::text,(payload->'tags')::text,''))
 FROM immich_sync.jobs WHERE asset_id IS NOT NULL;
COMMIT;"""
r=subprocess.run(KUBE+['-n','database','exec','-i','postgres-postgresql-0','--','psql','-XAtq','-v','ON_ERROR_STOP=1','-U','postgres','-d','photo_enrichment'],input=sql,text=True,capture_output=True,check=True)
records=[json.loads(line) for line in r.stdout.splitlines() if line.startswith('{')]
rows=sorted([row for row in records if row['kind']=='job'],key=lambda row:row['ordinal'])
descriptions={}
for row in records:
    if row['kind']=='description':descriptions.setdefault(row['asset_id'],[]).append(row['description'])
pattern=re.compile(r'\b(dogs?|pupp(?:y|ies)|canines?|waffles|husk(?:y|ies)|shepherds?|retrievers?)\b',re.I)
for row in rows:
    row['description']=' '.join(descriptions.get(row['asset_id'],[]))
    row['has_description']=bool((row['description'] or '').strip())
    row['dog_description']=bool(pattern.search(row['description'] or ''))
private=args.directory/'descriptions.json';private.write_text(json.dumps(rows)+'\n')
summary={}
for group,subset in [('all',rows),('matched',[r for r in rows if r['matched']]),('failed',[r for r in rows if r['status']=='failed'])]:
    summary[group]={'assets':len(subset),'with_description':sum(r['has_description'] for r in subset),'dog_description':sum(r['dog_description'] for r in subset)}
summary['query_vs_waffles_model']={f'query_{q}_model_{m}':sum(r['dog_description']==q and r['matched']==m for r in rows if r['status']=='complete') for q in [True,False] for m in [True,False]}
(args.directory/'description-coverage.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
