#!/usr/bin/env python3
"""Detect animal boxes on the exact visually reviewed image bytes, without writes."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
from distributed import KUBE

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);a=p.parse_args();os.umask(0o077)
 decisions=json.loads((a.directory/'visual-decisions.json').read_text());out=a.directory/'detections.json';saved=json.loads(out.read_text()) if out.exists() else {}
 pending=[]
 for index,row in decisions.items():
  if row['decision']!='accept' or index in saved:continue
  content=(a.directory/'targets'/(row['asset_id']+'.jpg')).read_bytes();assert hashlib.sha256(content).hexdigest()==row['image_sha256']
  pending.append({'review_index':int(index),'content':base64.b64encode(content).decode(),'sha256':row['image_sha256']})
 print('START: exact-byte animal-box detection for',len(pending),'visually accepted images; no metadata writes',flush=True)
 for start in range(0,len(pending),12):
  subset=pending[start:start+12]
  code='''import sys,json,base64,io,hashlib
sys.path.insert(0,'/app')
import torch;torch.set_num_threads(2)
from PIL import Image
import embedder,inference
rows=PAYLOAD
result=[]
with inference.inference_session():
 for row in rows:
  content=base64.b64decode(row['content']);assert hashlib.sha256(content).hexdigest()==row['sha256']
  image=Image.open(io.BytesIO(content)).convert('RGB')
  boxes=[[float(v) for v in box] for box,crop in embedder.crop_animals(image,conf=.25)]
  result.append({'review_index':row['review_index'],'sha256':row['sha256'],'size':list(image.size),'boxes':boxes})
print('BOX_RESULT '+json.dumps(result))
'''.replace('PAYLOAD',repr(subset))
  r=subprocess.run(KUBE+['-n','immich-pilot','exec','-i','deployment/immich-pet-tagger','--','python','-'],input=code,text=True,capture_output=True,timeout=240)
  (a.directory/f'detection-{start}.stdout').write_text(r.stdout);(a.directory/f'detection-{start}.stderr').write_text(r.stderr)
  marker=r.stdout.rfind('BOX_RESULT ')
  if r.returncode or marker<0:
   print(json.dumps({'detection_batch_failed':start,'returncode':r.returncode,'marker_present':marker>=0}),flush=True);continue
  rows=json.JSONDecoder().raw_decode(r.stdout[marker+len('BOX_RESULT '):])[0]
  saved.update({str(row['review_index']):row for row in rows});temp=out.with_suffix('.tmp');temp.write_text(json.dumps(saved,indent=2)+'\n');temp.replace(out)
  print(json.dumps({'detected':len(saved),'missing_boxes':sum(not row['boxes'] for row in saved.values())}),flush=True)

if __name__=='__main__':main()
