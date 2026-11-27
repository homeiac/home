#!/usr/bin/env python3
"""Freeze a reproducible private production sample and inspect media availability.

No Immich/queue writes. Images and asset identifiers remain in the private output.
Use --fetch after exporting to resume downloads; existing images are retained.
"""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import urllib.error
import urllib.request
from distributed import KUBE
from immich_client import BASE

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('directory',type=Path)
p.add_argument('--fetch',action='store_true')
args=p.parse_args();os.umask(0o077);args.directory.mkdir(parents=True,exist_ok=True)
manifest=args.directory/'sample.json'
if not manifest.exists():
    code='''import {createRequire} from 'node:module';
const {Client}=createRequire('/usr/src/app/server/package.json')('pg');const db=new Client();await db.connect();
await db.query('BEGIN READ ONLY');
const rows=(await db.query(`SELECT asset_id,worker,status,result,applied,ordinal,last_error
 FROM waffles.jobs WHERE run_id='historical-waffles' ORDER BY ordinal`)).rows;
await db.query('ROLLBACK');await db.end();console.log(JSON.stringify(rows));'''
    result=subprocess.run(KUBE+['-n','immich-pilot','exec','-i','deployment/waffles-queue','--','node','--input-type=module','-'],input=code,text=True,capture_output=True,check=True)
    rows=json.loads(result.stdout);rng=random.Random(24420261127);selected=[];seen=set()
    def take(group, candidates, count):
        candidates=[r for r in candidates if r['asset_id'] not in seen]
        for row in rng.sample(candidates,min(count,len(candidates))):
            selected.append({**row,'group':group});seen.add(row['asset_id'])
    matched=[r for r in rows if r['status']=='complete' and r['result']['matches']]
    for backend in ['mac','still-fawn','pve','fun-bedbug']:
        take('random_match_'+backend,[r for r in matched if r['worker']==backend],8)
    weak=sorted([r for r in matched if r['asset_id'] not in seen],key=lambda r:max(m['probability'] for m in r['result']['matches']))[:12]
    for row in weak:selected.append({**row,'group':'lowest_confidence_match'});seen.add(row['asset_id'])
    for group,key in [('rejected_low_confidence','low_confidence'),('rejected_unknown','unknown')]:
        take(group,[r for r in rows if r['status']=='complete' and not r['result']['matches'] and r['result'][key]>0],12)
    take('failed_preview',[r for r in rows if r['status']=='failed' and r['last_error']=='thumbnail_http_404'],32)
    for i,row in enumerate(selected):row['index']=i
    manifest.write_text(json.dumps(selected,indent=2)+'\n')
    (args.directory/'population.json').write_text(json.dumps({'total':len(rows),'matched':len(matched),'groups':dict(Counter(r['group'] for r in selected))},indent=2)+'\n')
items=json.loads(manifest.read_text())
print('START: frozen sample',len(items),'manifest_sha256',hashlib.sha256(manifest.read_bytes()).hexdigest(),flush=True)
if args.fetch:
    secret=json.loads(subprocess.check_output(KUBE+['-n','immich-pilot','get','secret','immich-pet-tagger','-o','json'],text=True))
    key=base64.b64decode(secret['data']['api-key']).decode()
    def request(path,download=False):
        req=urllib.request.Request(BASE+'/api'+path,headers={'x-api-key':key})
        try:
            with urllib.request.urlopen(req,timeout=30) as response:
                data=response.read(25*1024*1024+1) if download else b''
                if len(data)>25*1024*1024:return {'status':413,'type':response.headers.get('Content-Type')},None
                return {'status':response.status,'type':response.headers.get('Content-Type'),'length':response.headers.get('Content-Length')},data
        except urllib.error.HTTPError as error:return {'status':error.code},None
        except Exception as error:return {'status':0,'error':type(error).__name__},None
    def fetch(row):
        path=args.directory/f"{row['index']:03d}.media"
        statuses={};prefix='/assets/'+row['asset_id']
        for name,suffix in [('preview','/thumbnail?size=preview'),('thumbnail','/thumbnail?size=thumbnail'),('original','/original'),('playback','/video/playback')]:
            download=row['group']!='failed_preview' and not path.exists()
            result,data=request(prefix+suffix,download=download);statuses[name]=result
            if data and result.get('type','').startswith('image/'):
                path.write_bytes(data)
            if row['group']!='failed_preview' and path.exists():break
        return {'index':row['index'],'group':row['group'],'endpoints':statuses}
    reports=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for report in pool.map(fetch,items):
            reports.append(report)
            if len(reports)%10==0:print('PROGRESS:',len(reports),'/',len(items),flush=True)
    (args.directory/'availability.json').write_text(json.dumps(reports,indent=2)+'\n')
    print('DONE:',dict(Counter((r['group'],r['endpoints']['preview']['status']) for r in reports)),flush=True)
