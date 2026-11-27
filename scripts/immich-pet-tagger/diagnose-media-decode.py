#!/usr/bin/env python3
"""Capture bounded decoder diagnostics for failed videos without retaining original media."""
import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
from distributed import KUBE
p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);a=p.parse_args();os.umask(0o077)
assets=json.loads((a.directory/'assets.json').read_text())
code='''import fs from 'node:fs/promises';import {spawnSync} from 'node:child_process';
const rows=JSON.parse(Buffer.from(process.argv[2],'base64'));const results=[];
for(const [index,a] of rows.entries()){
if(a.type!=='VIDEO')continue;
const dir=await fs.mkdtemp('/dev/shm/decode-diagnostic-');
try{
const r=await fetch('http://immich-server.immich-pilot.svc.cluster.local:2283/api/assets/'+a.id+'/video/playback',{headers:{'x-api-key':process.env.IMMICH_API_KEY},signal:AbortSignal.timeout(20000)});
if(!r.ok)throw Error('http_'+r.status);if(Number(r.headers.get('content-length'))>128*1024*1024)throw Error('too_large');
const bytes=Buffer.from(await r.arrayBuffer());await fs.writeFile(dir+'/input',bytes);
const probe=spawnSync('ffprobe',['-v','error','-show_entries','stream=index,codec_type,codec_name,width,height,pix_fmt,color_range,color_space:format=format_name,duration','-of','json',dir+'/input'],{encoding:'utf8',timeout:15000,maxBuffer:65536});
const decode=spawnSync('ffmpeg',['-nostdin','-hide_banner','-loglevel','error','-threads','1','-i',dir+'/input','-map','0:v:0','-frames:v','1','-vf',"scale=w='min(1600,iw)':h='min(1600,ih)':force_original_aspect_ratio=decrease",'-threads','1','-q:v','2','-y',dir+'/frame.jpg'],{encoding:'utf8',timeout:15000,maxBuffer:65536});
results.push({index,bytes:bytes.length,header_hex:bytes.subarray(0,32).toString('hex'),zero_bytes:bytes.reduce((n,b)=>n+(b===0),0),probe_status:probe.status,probe:probe.stdout?JSON.parse(probe.stdout):{},probe_error:probe.stderr.replaceAll(dir,'TEMP'),decode_status:decode.status,decode_error:decode.stderr.replaceAll(dir,'TEMP')});
}finally{await fs.rm(dir,{recursive:true,force:true});}}
console.log(JSON.stringify(results));'''
print('START: reading video stream metadata and reproducing decoder errors',flush=True)
r=subprocess.run(KUBE+['-n','immich-pilot','exec','-i','deployment/waffles-queue','--','node','--input-type=module','-',base64.b64encode(json.dumps(assets).encode()).decode()],input=code,text=True,capture_output=True,check=True,timeout=240)
rows=json.loads(r.stdout);(a.directory/'decode-diagnostics.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(rows,indent=2))
