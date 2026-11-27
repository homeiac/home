#!/usr/bin/env python3
"""Exercise recovery against real assets, saving decoded frames privately; no writes to Immich."""
import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
from distributed import KUBE
p=argparse.ArgumentParser(description=__doc__);p.add_argument('manifest',type=Path);p.add_argument('directory',type=Path);p.add_argument('--count',type=int,default=8);args=p.parse_args()
os.umask(0o077);args.directory.mkdir(parents=True,exist_ok=True)
assets=json.loads(args.manifest.read_text())[:args.count]
module='data:text/javascript;base64,'+base64.b64encode(Path(__file__).with_name('media-fallback-core.mjs').read_bytes()).decode()
code='''import fs from 'node:fs/promises';import {recover} from MODULE;
const assets=JSON.parse(Buffer.from(process.argv[2],'base64'));const directory=await fs.mkdtemp('/dev/shm/waffles-probe-');const results=[];
try{for(let index=0;index<assets.length;index++){const started=Date.now();try{const r=await recover({base:'http://immich-server.immich-pilot.svc.cluster.local:2283',key:process.env.IMMICH_API_KEY,id:assets[index].id,directory});results.push({index,ok:true,source:r.source,seconds:(Date.now()-started)/1000,jpeg:r.bytes.toString('base64')});}catch(e){results.push({index,ok:false,status:e.status,reason:e.message});}}}finally{await fs.rm(directory,{recursive:true,force:true});}
console.log(JSON.stringify(results));'''.replace('MODULE',repr(module))
print('START: decoding',len(assets),'existing assets with the proposed fallback',flush=True)
r=subprocess.run(KUBE+['-n','immich-pilot','exec','-i','deployment/waffles-queue','--','node','--input-type=module','-',base64.b64encode(json.dumps(assets).encode()).decode()],input=code,text=True,capture_output=True,check=True,timeout=max(60,len(assets)*40))
results=json.loads(r.stdout)
for item in results:
    if 'jpeg' in item:(args.directory/f"{item['index']:03d}.jpg").write_bytes(base64.b64decode(item.pop('jpeg')))
(args.directory/'results.json').write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(results,indent=2))
