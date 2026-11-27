#!/usr/bin/env python3
"""Extract and validate genuine MP4 streams from linked motion originals; never overwrite sources."""
import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
from distributed import KUBE
p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);a=p.parse_args();os.umask(0o077)
parents=json.loads((a.directory/'motion-parents.json').read_text());diagnostics=json.loads((a.directory/'motion-source-diagnostics.json').read_text());meta=json.loads((a.directory/'original-metadata.json').read_text());videos={m['id']:m for m in meta if m['type']=='VIDEO'}
items=[{**parents[d['index']],'offsets':d['mp4_candidates'],'target':videos[parents[d['index']]['video_id']]['originalPath']} for d in diagnostics if d.get('mp4_candidates')]
code='''import fs from 'node:fs/promises';import crypto from 'node:crypto';import {spawnSync} from 'node:child_process';
const items=JSON.parse(Buffer.from(process.argv[2],'base64'));const out=[];
for(const [index,item] of items.entries()){
const input=await fs.readFile(item.path);const dir=await fs.mkdtemp('/tmp/waffles-motion-');
try{for(const offset of item.offsets){const clip=input.subarray(offset);await fs.writeFile(dir+'/candidate.mp4',clip);
const p=spawnSync('ffprobe',['-v','error','-show_entries','stream=codec_name,codec_type,width,height:format=duration','-of','json',dir+'/candidate.mp4'],{encoding:'utf8',timeout:15000,maxBuffer:65536});
// Decode every frame to a timestamp-free sink; muxer timestamp warnings are not pixel errors.
const d=spawnSync('ffmpeg',['-nostdin','-v','error','-xerror','-threads','1','-i',dir+'/candidate.mp4','-map','0:v:0','-f','rawvideo','-'],{encoding:'utf8',stdio:['ignore','ignore','pipe'],timeout:20000,maxBuffer:65536});
const valid=p.status===0&&d.status===0&&!d.stderr.trim();
let jpeg;
if(valid){const f=spawnSync('ffmpeg',['-nostdin','-v','error','-threads','1','-i',dir+'/candidate.mp4','-map','0:v:0','-frames:v','1','-vf',"scale=w='min(1600,iw)':h='min(1600,ih)':force_original_aspect_ratio=decrease",'-threads','1','-q:v','2','-y',dir+'/frame.jpg'],{timeout:15000,stdio:'ignore'});if(f.status!==0)throw Error('First-frame extraction failed');jpeg=(await fs.readFile(dir+'/frame.jpg')).toString('base64');}
out.push({index,video_id:item.video_id,parent_id:item.id,source_path:item.path,target_path:item.target,offset,bytes:clip.length,valid,probe:p.stdout?JSON.parse(p.stdout):{},decode_status:d.status,decode_error:d.stderr.replaceAll(dir,'TEMP'),source_sha256:crypto.createHash('sha256').update(input).digest('hex'),sha256:crypto.createHash('sha256').update(clip).digest('hex'),clip:valid?clip.toString('base64'):undefined,jpeg});
}}finally{await fs.rm(dir,{recursive:true,force:true});}}
console.log(JSON.stringify(out));'''
print('START: validating embedded MP4 candidates without changing Immich files',flush=True)
r=subprocess.run(KUBE+['-n','immich-pilot','exec','-i','deployment/immich-server','--','node','--input-type=module','-',base64.b64encode(json.dumps(items).encode()).decode()],input=code,text=True,capture_output=True,check=True,timeout=180)
rows=json.loads(r.stdout)
for row in rows:
    clip=row.pop('clip',None)
    if clip:(a.directory/f"motion-{row['index']}.mp4").write_bytes(base64.b64decode(clip))
    jpeg=row.pop('jpeg',None)
    if jpeg:(a.directory/f"motion-{row['index']}.jpg").write_bytes(base64.b64decode(jpeg))
    print(json.dumps({k:v for k,v in row.items() if k not in ('video_id','parent_id','source_path','target_path','source_sha256','sha256')}))
(a.directory/'motion-repair-plan.json').write_text(json.dumps(rows,indent=2)+'\n')
