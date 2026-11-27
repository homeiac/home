#!/usr/bin/env python3
"""Cache validated frames from recovered motion streams without changing original media."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
from distributed import KUBE,request
p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);p.add_argument('--apply',action='store_true');p.add_argument('--reuse-verified-existing',action='store_true');a=p.parse_args();os.umask(0o077)
plan=json.loads((a.directory/'motion-repair-plan.json').read_text())
items=[]
for row in plan:
    if not row['valid']:continue
    clip=(a.directory/f"motion-{row['index']}.mp4").read_bytes();assert hashlib.sha256(clip).hexdigest()==row['sha256']
    jpeg=(a.directory/f"motion-{row['index']}.jpg").read_bytes();assert jpeg[:2]==b'\xff\xd8' and jpeg[-2:]==b'\xff\xd9'
    items.append({'id':row['video_id'],'jpeg':base64.b64encode(jpeg).decode(),'metadata':{'source':'recovered_motion_video_first_frame','sha256':hashlib.sha256(jpeg).hexdigest(),'source_sha256':row['source_sha256'],'clip_sha256':row['sha256'],'parent_id':row['parent_id'],'offset':row['offset'],'full_decode_validated':True}})
assert items,'No validated frames'
if a.reuse_verified_existing:
    existing=json.loads((a.directory/'existing-cache.json').read_text())
    assert len(existing)==len(items)
    for index,item in enumerate(items):
        verified=(a.directory/f'existing-frame-{index}.jpg').read_bytes()
        assert hashlib.sha256(verified).hexdigest()==existing[index]['sha256']
        assert existing[index]['metadata']['source'] in ('embedded_video','live_photo_embedded_video','recovered_motion_video_first_frame')
        item['acceptedExistingHash']=existing[index]['sha256']
print(json.dumps({'validated_frames':len(items),'apply':a.apply}),flush=True)
if not a.apply:raise SystemExit(0)
code='''import fs from 'node:fs/promises';import crypto from 'node:crypto';
const items=ITEMS;const root=process.env.MEDIA_CACHE??'/data/frames-v1';let installed=0,existing=0;
for(const item of items){
if(!/^[0-9a-f-]{36}$/.test(item.id))throw Error('Invalid asset identifier');
const bytes=Buffer.from(item.jpeg,'base64');if(crypto.createHash('sha256').update(bytes).digest('hex')!==item.metadata.sha256)throw Error('Frame checksum mismatch');
const path=root+'/'+item.id+'.jpg';
try{const old=await fs.readFile(path);if(!old.equals(bytes)&&crypto.createHash('sha256').update(old).digest('hex')!==item.acceptedExistingHash)throw Error('Refusing to overwrite a different cached frame');existing++;continue;}catch(e){if(e.code!=='ENOENT')throw e;}
const temporary=path+'.repair-'+crypto.randomUUID();
await fs.writeFile(temporary,bytes,{flag:'wx'});
await fs.writeFile(path+'.json',JSON.stringify({...item.metadata,created_at:new Date().toISOString()}),{flag:'wx'});
try{await fs.link(temporary,path);}finally{await fs.unlink(temporary);}
installed++;
}console.log(JSON.stringify({installed,existing}));'''.replace('ITEMS',json.dumps(items))
r=subprocess.run(KUBE+['-n','immich-pilot','exec','-i','deployment/waffles-media','--','node','--input-type=module','-'],input=code,text=True,capture_output=True,timeout=60)
if r.returncode:
    (a.directory/'cache-install-error.txt').write_text(r.stderr)
    safe=r.stderr
    for item in items:safe=safe.replace(item['id'],'ASSET').replace(item['jpeg'],'JPEG')
    raise SystemExit(safe[-1500:])
print(r.stdout.strip())
assets={r['id']:r for r in json.loads((a.directory/'assets.json').read_text())}
selected=[assets[i['id']] for i in items];run='waffles-motion-recovery-20261127'
if not any(r['id']==run for r in request('/admin/status')['runs']):request('/admin/run',{'id':run,'mode':'production','workers':['mac','still-fawn','pve','fun-bedbug'],'assets':[{'id':r['id'],'date':r['date']} for r in selected]})
request('/admin/state',{'id':run,'state':'running'})
(a.directory/'motion-run.json').write_text(json.dumps({'run':run,'assets':len(items),'frame_sha256':[i.get('acceptedExistingHash',i['metadata']['sha256']) for i in items]})+'\n')
print(json.dumps({'run':run,'assets':len(items),'submitted':True}))
