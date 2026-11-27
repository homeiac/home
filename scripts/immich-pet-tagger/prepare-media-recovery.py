#!/usr/bin/env python3
"""Freeze failed assets for an auditable recovery run, prioritizing dog descriptions."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re
import subprocess
from distributed import KUBE
p=argparse.ArgumentParser(description=__doc__);p.add_argument('quality_directory',type=Path);p.add_argument('directory',type=Path);args=p.parse_args()
os.umask(0o077);args.directory.mkdir(parents=True,exist_ok=True)
target=args.directory/'assets.json'
if target.exists():raise SystemExit('Frozen recovery manifest already exists')
code='''import {createRequire} from 'node:module';const {Client}=createRequire('/usr/src/app/server/package.json')('pg');const db=new Client();await db.connect();
await db.query('BEGIN READ ONLY');const rows=(await db.query("SELECT asset_id,taken_at,ordinal FROM waffles.jobs WHERE run_id='historical-waffles' AND status='failed' AND last_error='thumbnail_http_404' ORDER BY ordinal")).rows;
await db.query('ROLLBACK');await db.end();console.log(JSON.stringify(rows));'''
r=subprocess.run(KUBE+['-n','immich-pilot','exec','-i','deployment/waffles-queue','--','node','--input-type=module','-'],input=code,text=True,capture_output=True,check=True)
rows=json.loads(r.stdout);descriptions={r['asset_id']:r for r in json.loads((args.quality_directory/'descriptions.json').read_text())}
inventory={r['id']:r for r in json.loads((args.quality_directory.parent/'distributed/inventory.json').read_text())}
pattern=re.compile(r'\b(dogs?|pupp(?:y|ies)|canines?|husk(?:y|ies)|shepherds?|retrievers?)\b',re.I)
assets=[]
for row in rows:
    d=descriptions[row['asset_id']];priority=0 if pattern.search(d['description'] or '') else 1 if not d['has_description'] else 2
    assets.append({'id':row['asset_id'],'date':row['taken_at'],'ordinal':row['ordinal'],'priority':priority,'type':inventory[row['asset_id']]['type']})
assets.sort(key=lambda r:(r['priority'],r['ordinal']));target.write_text(json.dumps(assets,indent=2)+'\n')
print(json.dumps({'assets':len(assets),'types':dict(Counter(r['type'] for r in assets)),'priority_counts':dict(Counter(r['priority'] for r in assets))}))
