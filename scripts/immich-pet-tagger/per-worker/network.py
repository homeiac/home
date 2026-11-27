#!/usr/bin/env python3
"""Compare fresh versus pooled requests for identical holdout preview endpoints.

No inference or Immich writes. Credentials read into memory and sent via stdin
only. Both modes fully consume responses; content hashes detect changed payloads.
"""
import argparse,subprocess,json,sys,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from distributed import KUBE,BASE,secret
p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);p.add_argument('backend',choices=['mac','still-fawn']);a=p.parse_args();os.umask(0o077)
truth=json.loads((a.directory.parent/'owner-confirmed-holdout.json').read_text());assets=truth['positive']+truth['negative']
payload={'base':BASE if a.backend=='mac' else 'http://waffles-queue.immich-pilot.svc.cluster.local:9200','token':secret('worker-token'),'assets':assets}
code='''import sys,json,time,hashlib,requests
p=json.load(sys.stdin);rows=[]
for rep in range(2):
 for mode in (['fresh','pooled'] if rep==0 else ['pooled','fresh']):
  session=requests.Session()
  try:
   for i in (range(len(p['assets'])) if rep==0 else reversed(range(len(p['assets'])))):
    start=time.perf_counter()
    r=(session.get if mode=='pooled' else requests.get)(p['base']+'/immich/api/assets/'+p['assets'][i]+'/thumbnail?size=preview',headers={'Authorization':'Bearer '+p['token']},timeout=20)
    content=r.content;r.raise_for_status();r.close()
    rows.append({'pass':rep,'mode':mode,'index':i,'seconds':time.perf_counter()-start,'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()})
  finally:session.close()
print(json.dumps(rows))'''
command=KUBE+['-n','immich-pilot','exec','-i','deployment/immich-pet-tagger','--','python','-c',code] if a.backend=='still-fawn' else [str(Path.home()/'Library/Application Support/immich-pet-tagger/venv/bin/python'),'-c',code]
print('START network comparison',a.backend,flush=True)
r=subprocess.run(command,input=json.dumps(payload),text=True,capture_output=True,timeout=300)
(a.directory/(a.backend+'-network.stderr')).write_text(r.stderr)
if r.returncode:raise RuntimeError('Network comparison failed; diagnostics private')
rows=json.loads(r.stdout);(a.directory/(a.backend+'-network.json')).write_text(json.dumps(rows,indent=2)+'\n')
print('COMPLETE',len(rows),'bounded requests',flush=True)
