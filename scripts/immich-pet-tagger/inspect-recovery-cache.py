#!/usr/bin/env python3
"""Inspect existing cache provenance before replacing or reusing recovery frames."""
import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
from distributed import KUBE
p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);a=p.parse_args();os.umask(0o077)
plan=json.loads((a.directory/'motion-repair-plan.json').read_text());ids=[r['video_id'] for r in plan if r['valid']]
code='''import fs from 'node:fs/promises';import crypto from 'node:crypto';const ids=JSON.parse(Buffer.from(process.argv[2],'base64'));const out=[];
for(const [index,id] of ids.entries()){const path='/data/frames-v1/'+id+'.jpg';try{const bytes=await fs.readFile(path);let metadata;try{metadata=JSON.parse(await fs.readFile(path+'.json','utf8'));}catch{}out.push({index,bytes:bytes.length,sha256:crypto.createHash('sha256').update(bytes).digest('hex'),metadata,jpeg:bytes.toString('base64')});}catch(e){out.push({index,error:e.code});}}console.log(JSON.stringify(out));'''
r=subprocess.run(KUBE+['-n','immich-pilot','exec','-i','deployment/waffles-media','--','node','--input-type=module','-',base64.b64encode(json.dumps(ids).encode()).decode()],input=code,text=True,capture_output=True,check=True)
rows=json.loads(r.stdout)
for r in rows:
    if 'jpeg' in r:(a.directory/f"existing-frame-{r['index']}.jpg").write_bytes(base64.b64decode(r.pop('jpeg')))
    print(json.dumps({k:v for k,v in r.items() if k!='metadata'}|{'metadata':{k:v for k,v in r.get('metadata',{}).items() if k not in ('parent_id','asset_id')}}))
(a.directory/'existing-cache.json').write_text(json.dumps(rows,indent=2)+'\n')
