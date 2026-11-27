#!/usr/bin/env python3
"""Compare frozen and freshly fitted classifiers inside the original CPU deployment."""
import argparse
import json
from pathlib import Path
import subprocess
from distributed import KUBE

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('directory',type=Path)
args=parser.parse_args()
old=next(json.loads(line) for line in (args.directory/'evaluation-verified.log').read_text().splitlines() if line.startswith('{"counts"'))
payload=dict(config=json.loads((args.directory/'distributed/classifier.json').read_text()),ids=[r['asset'] for r in old['results'] if r['expected']=='positive' and r['matched']])
code='''import sys,json
sys.path.insert(0,'/app')
import numpy as np
from pathlib import Path
import classifier,data,embedder,inference
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
payload=json.loads(sys.argv[1]); frozen=payload['config']; directory=Path('/data')
embedder.load_embed_cache(directory)
model=LogisticRegression();scaler=StandardScaler()
for obj,values in [(model,frozen['model']),(scaler,frozen['scaler'])]:
 for k,v in values.items():setattr(obj,k,np.array(v) if isinstance(v,list) else v)
config=data.load_config(directory)
refs={n:data.load_pet_refs(c['person_id'],directory) for n,c in config.items()}
with inference.inference_session():
 names,fresh,scale=classifier.build_classifier(list(config),refs,data.load_negatives(directory))
 print(json.dumps(dict(coef_max_difference=float(np.max(np.abs(fresh.coef_-model.coef_))),scaler_max_difference=float(np.max(np.abs(scale.mean_-scaler.mean_))))),flush=True)
 for i,asset in enumerate(payload['ids']):
  img=embedder.fetch_thumbnail(asset);results=[]
  for box,crop in embedder.crop_animals(img,conf=.25) or [(None,img)]:
   vec=embedder.embed_image(crop)
   a,pa=classifier.classify(vec,names,fresh,scale);b,pb=classifier.classify(vec,frozen['names'],model,scaler)
   results.append(dict(detected=box is not None,fresh_name=a,fresh_probability=pa,frozen_name=b,frozen_probability=pb))
  print(json.dumps(dict(example=i,predictions=results)),flush=True)
'''
# Private IDs and numeric classifier parameters go through stdin, never command arguments.
wrapper='import sys\nsys.argv=["diagnose",'+repr(json.dumps(payload))+']\n'+code
result=subprocess.run(KUBE+['-n','immich-pilot','exec','-i','deployment/immich-pet-tagger','--','python','-'],input=wrapper,text=True,capture_output=True)
print(result.stdout)
if result.returncode: raise RuntimeError('Classifier diagnostic failed; private stderr suppressed')
