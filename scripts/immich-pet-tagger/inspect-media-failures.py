#!/usr/bin/env python3
"""Audit failed recovery assets; retain identifiers privately and print only diagnostics."""
import argparse
import json
import os
from pathlib import Path
import subprocess
from distributed import KUBE
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('directory',type=Path)
p.add_argument('--run',default='waffles-media-recovery-20261127')
a=p.parse_args();os.umask(0o077);a.directory.mkdir(parents=True,exist_ok=True)
code='''import {createRequire} from 'node:module';const {Client}=createRequire('/usr/src/app/server/package.json')('pg');
const db=new Client();await db.connect();
const rows=(await db.query("SELECT asset_id, taken_at, ordinal, worker, attempts, apply_attempts, last_error FROM waffles.jobs WHERE run_id=$1 AND status='failed' ORDER BY ordinal",[process.argv[2]])).rows;
await db.end();
const base='http://immich-server.immich-pilot.svc.cluster.local:2283/api/assets/';
for(const [index,row] of rows.entries()){
row.index=index;const options={headers:{'x-api-key':process.env.IMMICH_API_KEY},redirect:'manual',signal:AbortSignal.timeout(20000)};
const r=await fetch(base+row.asset_id,options);row.metadata_status=r.status;
if(r.ok){const a=await r.json();Object.assign(row,{type:a.type,isOffline:a.isOffline,isTrashed:a.isTrashed,bytes:a.exifInfo?.fileSizeInByte});}else await r.body?.cancel();
row.routes={};for(const suffix of ['thumbnail?size=preview','thumbnail?size=thumbnail','thumbnail?size=fullsize',row.type==='VIDEO'?'video/playback':'original']){
try{const r=await fetch(base+row.asset_id+'/'+suffix,{...options,signal:AbortSignal.timeout(20000)});row.routes[suffix]={status:r.status,bytes:r.headers.get('content-length'),type:r.headers.get('content-type'),redirect:!!r.headers.get('location')};await r.body?.cancel();}catch(e){row.routes[suffix]={error:e.name};}}
}console.log(JSON.stringify(rows));'''
print('START: inspecting failed assets and media routes',flush=True)
r=subprocess.run(KUBE+['-n','immich-pilot','exec','-i','deployment/waffles-queue','--','node','--input-type=module','-',a.run],input=code,text=True,capture_output=True,check=True,timeout=240)
rows=json.loads(r.stdout)
(a.directory/'failure-details.json').write_text(json.dumps(rows,indent=2)+'\n')
(a.directory/'assets.json').write_text(json.dumps([{'id':r['asset_id'],'date':r['taken_at'],'type':r.get('type')} for r in rows],indent=2)+'\n')
for r in rows:print(json.dumps({k:v for k,v in r.items() if k not in ('asset_id','taken_at')}))
