#!/usr/bin/env python3
"""Inspect original files read-only through Immich's existing mounted library."""
import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
from distributed import KUBE
from immich_client import api
p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);a=p.parse_args();os.umask(0o077)
assets=json.loads((a.directory/'assets.json').read_text())
metadata=[api('/assets/'+v['id']) for v in assets]
(a.directory/'original-metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
items=[{'path':m['originalPath'],'type':m['type']} for m in metadata]
code='''import fs from 'node:fs/promises';import path from 'node:path';import crypto from 'node:crypto';import {createRequire} from 'node:module';import {spawnSync} from 'node:child_process';
const sharp=createRequire('/usr/src/app/server/package.json')('sharp');
const items=JSON.parse(Buffer.from(process.argv[2],'base64'));const out=[];
for(const [index,item] of items.entries()){
const s=await fs.stat(item.path);const f=await fs.open(item.path,'r');const header=Buffer.alloc(32);await f.read(header,0,32,0);await f.close();
const row={index,type:item.type,extension:path.extname(item.path),bytes:s.size,header_hex:header.toString('hex'),external:item.path.startsWith('/external/')};
if(s.size<=128*1024*1024){const b=await fs.readFile(item.path);row.sha256=crypto.createHash('sha256').update(b).digest('hex');}
if(item.type==='IMAGE'){try{const m=await sharp(item.path,{limitInputPixels:40000000}).metadata();row.image={format:m.format,width:m.width,height:m.height};}catch(e){row.image_error=e.message.replaceAll(item.path,'SOURCE');}}
else {const p=spawnSync('ffprobe',['-v','error','-show_entries','stream=codec_type,codec_name,width,height','-of','json',item.path],{encoding:'utf8',timeout:15000,maxBuffer:65536});row.probe_status=p.status;row.probe=p.stdout?JSON.parse(p.stdout):{};row.probe_error=p.stderr.replaceAll(item.path,'SOURCE');}
out.push(row);
}console.log(JSON.stringify(out));'''
print('START: verifying original source files read-only; no source writes',flush=True)
r=subprocess.run(KUBE+['-n','immich-pilot','exec','-i','deployment/immich-server','--','node','--input-type=module','-',base64.b64encode(json.dumps(items).encode()).decode()],input=code,text=True,capture_output=True,check=True,timeout=180)
rows=json.loads(r.stdout);(a.directory/'original-diagnostics.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(rows,indent=2))
