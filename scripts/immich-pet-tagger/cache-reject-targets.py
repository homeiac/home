#!/usr/bin/env python3
"""Freeze private thumbnails for the approved reject review; no external model calls."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.request
from distributed import BASE,secret
p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);a=p.parse_args();os.umask(0o077)
rows=json.loads((a.directory/'rejects.json').read_text());directory=a.directory/'targets';directory.mkdir(exist_ok=True);token=secret('worker-token')
def fetch(row:dict)->dict:
    asset=row['asset_id'];path=directory/(asset+'.jpg')
    for attempt in range(2):
        try:
            if not path.exists():
                req=urllib.request.Request(BASE+'/immich/api/assets/'+asset+'/thumbnail',headers={'Authorization':'Bearer '+token})
                with urllib.request.urlopen(req,timeout=35) as response:content=response.read(16*1024*1024+1)
                if len(content)>16*1024*1024:raise ValueError('Oversize review image')
                temporary=path.with_suffix('.tmp');temporary.write_bytes(content);temporary.replace(path)
            content=path.read_bytes();return {'asset_id':asset,'index':row['review_index'],'sha256':hashlib.sha256(content).hexdigest(),'bytes':len(content),'ok':True}
        except Exception as e:
            if attempt:return {'asset_id':asset,'index':row['review_index'],'ok':False,'error':type(e).__name__}
            time.sleep(1)
    raise AssertionError('Unreachable')
print(json.dumps({'event':'start','targets':len(rows),'workers':4,'external_model_calls':0}),flush=True)
results=[]
with ThreadPoolExecutor(max_workers=4) as pool:
    for future in as_completed([pool.submit(fetch,r) for r in rows]):
        results.append(future.result())
        if len(results)%50==0 or len(results)==len(rows):print(json.dumps({'cached':len(results),'errors':sum(not r['ok'] for r in results)}),flush=True)
(a.directory/'target-hashes.json').write_text(json.dumps(sorted(results,key=lambda r:r['index']),indent=2)+'\n')
