#!/usr/bin/env python3
"""Freeze query/model disagreement samples for independent private visual labels."""
import argparse
import base64
import json
import os
from pathlib import Path
import random
import subprocess
from distributed import KUBE
p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('directory',type=Path);args=p.parse_args()
os.umask(0o077);args.directory.mkdir(parents=True,exist_ok=True)
target=args.directory/'sample.json'
if target.exists():raise SystemExit('Frozen sample already exists')
rows=json.loads((args.source/'descriptions.json').read_text());rng=random.Random(24420261128)
groups=[('query_dog_model_no',True,False,32),('query_no_model_waffles',False,True,100),('query_no_model_no',False,False,24)]
selected=[]
for group,q,m,n in groups:
    candidates=[r for r in rows if r['status']=='complete' and r['dog_description']==q and r['matched']==m]
    for row in rng.sample(candidates,min(n,len(candidates))):selected.append({**row,'group':group})
ids=[r['asset_id'] for r in selected]
code='''import {createRequire} from 'node:module';const {Client}=createRequire('/usr/src/app/server/package.json')('pg');
const db=new Client();await db.connect();const ids=JSON.parse(Buffer.from(process.argv[2],'base64'));
const rows=(await db.query("SELECT asset_id,worker,result,applied FROM waffles.jobs WHERE run_id='historical-waffles' AND asset_id=ANY($1::uuid[])",[ids])).rows;
await db.end();console.log(JSON.stringify(rows));'''
r=subprocess.run(KUBE+['-n','immich-pilot','exec','-i','deployment/waffles-queue','--','node','--input-type=module','-',base64.b64encode(json.dumps(ids).encode()).decode()],input=code,text=True,capture_output=True,check=True)
details={r['asset_id']:r for r in json.loads(r.stdout)}
for i,row in enumerate(selected):row.update(details[row['asset_id']]);row['index']=i
target.write_text(json.dumps(selected,indent=2)+'\n');print('Frozen',len(selected),'query audit examples')
