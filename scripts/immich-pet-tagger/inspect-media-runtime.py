#!/usr/bin/env python3
"""Inspect pinned queue image media tools without reading private media or keys."""
import subprocess
from distributed import KUBE
code='''import {createRequire} from 'node:module';import {spawnSync} from 'node:child_process';
const require=createRequire('/usr/src/app/server/package.json');
for(const name of ['sharp']){try{const m=require(name);console.log(name,JSON.stringify(m.versions));}catch{console.log(name,'unavailable');}}
for(const name of ['ffmpeg','ffprobe']){const r=spawnSync(name,['-version'],{encoding:'utf8'});console.log(name,r.status,(r.stdout??'').split('\\n')[0]);}'''
subprocess.run(KUBE+['-n','immich-pilot','exec','-i','deployment/waffles-queue','--','node','--input-type=module','-'],input=code,text=True,check=True)
