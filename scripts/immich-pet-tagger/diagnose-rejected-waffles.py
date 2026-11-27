#!/usr/bin/env python3
"""Replay the nine reviewed misses with the frozen classifier, recording crop and score gates."""
import argparse
import json
import os
from pathlib import Path
import subprocess
from distributed import KUBE
p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);a=p.parse_args();os.umask(0o077)
misses=json.loads((a.directory/'nine-misses.json').read_text());config=json.loads((a.directory.parent/'distributed/classifier.json').read_text())
payload={'config':config,'samples':[{'asset':r['asset_id'],'audit_index':r['index'],'stored':r['result'],'worker':r['worker']} for r in misses]}
code='''import sys,json,logging
sys.path.insert(0,'/app')
import torch;torch.set_num_threads(2)
import numpy as np
from pathlib import Path
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
import classifier,embedder,inference
payload=PAYLOAD
config=payload['config'];scaler=StandardScaler();model=LogisticRegression()
for obj,values in [(scaler,config['scaler']),(model,config['model'])]:
 for key,value in values.items():setattr(obj,key,np.asarray(value) if isinstance(value,list) else value)
for name in ['embedder','immich','detector']:logging.getLogger(name).setLevel(logging.ERROR)
rows=[]
with inference.inference_session():
 for sample in payload['samples']:
  image=embedder.fetch_thumbnail(sample['asset'])
  if image is None:raise RuntimeError('Missing review image')
  predictions=[]
  for box,crop in embedder.crop_animals(image,conf=.25) or [(None,image)]:
   vector=embedder.embed_image(crop)
   if vector is None:raise RuntimeError('Embedding failed')
   name,score=classifier.classify(vector,config['names'],model,scaler)
   predictions.append({'name':name,'probability':float(score),'detected':box is not None,'box':[float(v) for v in box] if box is not None else None,'accepted':name=='Waffles' and box is not None and score>=.90})
  rows.append({**sample,'size':list(image.size),'predictions':predictions})
print('REVIEW_RESULT '+json.dumps(rows))
'''.replace('PAYLOAD',repr(payload))
print('START: replaying nine misses with frozen weights; no tag writes or threshold changes',flush=True)
r=subprocess.run(KUBE+['-n','immich-pilot','exec','-i','deployment/immich-pet-tagger','--','python','-'],input=code,text=True,capture_output=True,timeout=240)
(a.directory/'local-replay.stdout').write_text(r.stdout);(a.directory/'local-replay.stderr').write_text(r.stderr)
if r.returncode:raise SystemExit('Replay failed; private diagnostics saved')
rows=json.loads(next(s.removeprefix('REVIEW_RESULT ') for s in r.stdout.splitlines() if s.startswith('REVIEW_RESULT ')))
(a.directory/'nine-replay.json').write_text(json.dumps(rows,indent=2)+'\n')
for row in rows:print(json.dumps({k:v for k,v in row.items() if k not in ('asset','stored')}))
