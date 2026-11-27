#!/usr/bin/env python3
"""Find same-named source copies for failed managed videos, without changing any files."""
import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
from distributed import KUBE
p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);a=p.parse_args();os.umask(0o077)
metadata=json.loads((a.directory/'original-metadata.json').read_text())
items=[{'index':i,'name':m.get('originalFileName'),'type':m['type'],'managed':not m['originalPath'].startswith('/external/'),'root':'/'.join(m['originalPath'].split('/')[:3])} for i,m in enumerate(metadata)]
code='''import fs from 'node:fs/promises';import path from 'node:path';import {spawnSync} from 'node:child_process';
const items=JSON.parse(Buffer.from(process.argv[2],'base64'));const candidates=[];const wanted=items;let visited=0;
async function walk(dir){for(const e of await fs.readdir(dir,{withFileTypes:true})){const p=path.join(dir,e.name);if(e.isDirectory())await walk(p);else if(e.isFile()){visited++;for(const i of wanted)if(e.name===i.name)candidates.push({index:i.index,path:p});}}}
await walk('/external/gphotos/Google Photos');
for(const c of candidates){const s=await fs.stat(c.path);c.bytes=s.size;const p=spawnSync('ffprobe',['-v','error','-show_entries','stream=codec_type,codec_name,width,height','-of','json',c.path],{encoding:'utf8',timeout:15000,maxBuffer:65536});c.valid=p.status===0;c.probe=p.stdout?JSON.parse(p.stdout):{};}
console.log(JSON.stringify({visited,items,candidates}));'''
print('START: checking original filenames and searching the read-only source library for copies',flush=True)
r=subprocess.run(KUBE+['-n','immich-pilot','exec','-i','deployment/immich-server','--','node','--input-type=module','-',base64.b64encode(json.dumps(items).encode()).decode()],input=code,text=True,capture_output=True,check=True,timeout=180)
data=json.loads(r.stdout);(a.directory/'source-copies.json').write_text(json.dumps(data,indent=2)+'\n')
print(json.dumps({'files_checked':data['visited'],'sources':data['items'],'candidates':[{'index':c['index'],'bytes':c['bytes'],'valid':c['valid']} for c in data['candidates']]},indent=2))
