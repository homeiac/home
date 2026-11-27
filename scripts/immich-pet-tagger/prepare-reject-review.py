#!/usr/bin/env python3
"""Freeze dog-labelled model rejects and inspect prior blinded evaluation evidence."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import urllib.request
from distributed import BASE,secret
p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);a=p.parse_args();os.umask(0o077);a.directory.mkdir(parents=True,exist_ok=True);root=a.directory.parent
records=json.loads((root/'final-coverage-20261127/database-export.json').read_text());final=json.loads((root/'final-coverage-20261127/final-assets.json').read_text())
pattern=re.compile(r'\b(dogs?|pupp(?:y|ies)|canines?|husk(?:y|ies)|shepherds?|retrievers?)\b',re.I)
captions={}
for r in records:
    if r['kind']=='description':captions[r['asset_id']]=captions.get(r['asset_id'],'')+' '+r['description']
rejects=[r for r in final if r['status']=='complete' and not r['matched'] and pattern.search(captions.get(r['asset_id'],''))]
for i,r in enumerate(rejects):r['review_index']=i
manifest=a.directory/'rejects.json'
encoded=json.dumps(rejects,sort_keys=True,indent=2)+'\n'
if manifest.exists():assert manifest.read_text()==encoded,'Frozen cohort changed'
else:manifest.write_text(encoded)
misses=json.loads((root/'final-coverage-20261127/visually-reviewed-misses.json').read_text());(a.directory/'nine-misses.json').write_text(json.dumps(misses,indent=2)+'\n')
selection=json.loads((root/'selection.json').read_text());holdout=json.loads((root/'owner-confirmed-holdout.json').read_text());holdout_ids=set(holdout['positive']+holdout['negative']);references=[r for r in selection['references'] if r not in holdout_ids]
assert references and not set(references)&holdout_ids
(a.directory/'reference-candidates.json').write_text(json.dumps(references)+'\n')
refs=a.directory/'references';refs.mkdir(exist_ok=True);token=secret('worker-token')
def fetch(item):
    i,asset=item;target=refs/f'{i:02}.jpg'
    if not target.exists():
        req=urllib.request.Request(BASE+'/immich/api/assets/'+asset+'/thumbnail',headers={'Authorization':'Bearer '+token})
        with urllib.request.urlopen(req,timeout=40) as r:target.write_bytes(r.read())
with ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(fetch,enumerate(references)))
print(json.dumps({'rejects':len(rejects),'media':dict(Counter(r['type'] for r in rejects)),'original_outcomes':dict(Counter(r['outcome'] for r in rejects)),
    'nine_stored_outcomes':[{'audit_index':r['index'],'worker':r['worker'],'unknown':r['result']['unknown'],'low_confidence':r['result']['low_confidence']} for r in misses],
    'reference_candidates':len(references),'manifest_sha256':hashlib.sha256(manifest.read_bytes()).hexdigest()},indent=2))
for model in ['luna','sol']:
    results=[json.loads(f.read_text()) for f in sorted((root/f'frontier-{model}').glob('*/result.json'))]
    print(json.dumps({'previous_model':model,'positive_answer_examples':[r['answer'] for r in results if r['expected']=='positive'][:5]},indent=2))
