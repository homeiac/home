#!/usr/bin/env python3
"""Validate linked stills, embedded MP4 signatures and their existing Waffles results."""
import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
from distributed import KUBE
p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);a=p.parse_args();os.umask(0o077)
parents=json.loads((a.directory/'motion-parents.json').read_text())
metadata=json.loads((a.directory/'original-metadata.json').read_text())
items=parents+[{'id':m['id'],'path':m['originalPath']} for m in metadata if m['type']=='IMAGE']
code='''import fs from 'node:fs/promises';import {createRequire} from 'node:module';
const sharp=createRequire('/usr/src/app/server/package.json')('sharp');const items=JSON.parse(Buffer.from(process.argv[2],'base64'));const out=[];
for(const [index,i] of items.entries()){
try {
const s=await fs.stat(i.path);if(s.size>128*1024*1024)throw Error('Source exceeds probe bound');const bytes=await fs.readFile(i.path);
const positions=[];for(let p=bytes.indexOf('ftyp');p!==-1;p=bytes.indexOf('ftyp',p+4)){if(p>=4){const size=bytes.readUInt32BE(p-4);if(size>=16&&size<=4096&&p-4+size<=bytes.length)positions.push(p-4);}}
const row={index,id:i.id,bytes:bytes.length,mp4_candidates:positions};
try{const converted=await sharp(bytes,{limitInputPixels:40000000}).rotate().resize({width:1600,height:1600,fit:'inside',withoutEnlargement:true}).jpeg({quality:90}).toBuffer();row.image_decode_ok=true;row.jpeg_bytes=converted.length;}catch(e){row.image_decode_ok=false;row.image_error=e.message;}
out.push(row);
}catch(e){out.push({index,id:i.id,error:e.code??e.name});}
}console.log(JSON.stringify(out));'''
r=subprocess.run(KUBE+['-n','immich-pilot','exec','-i','deployment/immich-server','--','node','--input-type=module','-',base64.b64encode(json.dumps(items).encode()).decode()],input=code,text=True,capture_output=True,timeout=180)
if r.returncode:
    (a.directory/'motion-probe-error.txt').write_text(r.stderr)
    safe=r.stderr
    for item in items:safe=safe.replace(item['path'],'SOURCE').replace(item['id'],'ASSET')
    raise SystemExit(safe[-2000:])
rows=json.loads(r.stdout)
code='''import {createRequire} from 'node:module';const {Client}=createRequire('/usr/src/app/server/package.json')('pg');const db=new Client();await db.connect();const ids=JSON.parse(Buffer.from(process.argv[2],'base64'));console.log(JSON.stringify((await db.query("SELECT asset_id,status,last_error,coalesce(jsonb_array_length(result->'matches'),0) AS matches FROM waffles.jobs WHERE run_id='historical-waffles' AND asset_id=ANY($1::uuid[])",[ids])).rows));await db.end();'''
r=subprocess.run(KUBE+['-n','immich-pilot','exec','-i','deployment/waffles-queue','--','node','--input-type=module','-',base64.b64encode(json.dumps([i['id'] for i in items]).encode()).decode()],input=code,text=True,capture_output=True,check=True)
results={r['asset_id']:r for r in json.loads(r.stdout)}
for row in rows:row['historical']={k:v for k,v in results.get(row['id'],{}).items() if k!='asset_id'}
(a.directory/'motion-source-diagnostics.json').write_text(json.dumps(rows,indent=2)+'\n')
for row in rows:print(json.dumps({k:v for k,v in row.items() if k!='id'}))
