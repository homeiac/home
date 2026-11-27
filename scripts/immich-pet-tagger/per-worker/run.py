#!/usr/bin/env python3
"""Launch one isolated matched-photo worker and sample its real process."""
import argparse,json,subprocess,sys,time,tarfile,io,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from distributed import KUBE
p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);p.add_argument('backend',choices=['mac-cpu','mac-mps','still-fawn']);p.add_argument('--threads',type=int,default=2);p.add_argument('--label',required=True);p.add_argument('--pause',type=int,default=0);p.add_argument('--inflight',type=int,default=1);p.add_argument('--cpu-detector',action='store_true');a=p.parse_args();os.umask(0o077)
a.directory=a.directory.resolve();runtime=Path.home()/'Library/Application Support/immich-pet-tagger'
if a.backend=='still-fawn':
 remote='/tmp/waffles-per-worker-20261127'
 # Ship only frozen approved bytes and the diagnostic code, never credentials.
 data=io.BytesIO()
 with tarfile.open(fileobj=data,mode='w') as tar:
  for name in ['images','manifest.json','classifier.json','worker.py']:tar.add(a.directory/name,arcname=name)
 unpack="import tarfile,sys,pathlib;root=pathlib.Path('/tmp/waffles-per-worker-20261127');root.mkdir(exist_ok=True);tarfile.open(fileobj=sys.stdin.buffer,mode='r|').extractall(root,filter='data')"
 subprocess.run(KUBE+['-n','immich-pilot','exec','-i','deployment/immich-pet-tagger','--','python','-c',unpack],input=data.getvalue(),check=True,timeout=90)
 find="from pathlib import Path;import json;print(json.dumps({'yolo':str(next(Path('/data').rglob('yolov8n.pt'))),'clip':str(next(Path('/data').rglob('ViT-B-16.pt')))}))"
 r=subprocess.check_output(KUBE+['-n','immich-pilot','exec','deployment/immich-pet-tagger','--','python','-c',find],text=True,timeout=30);paths=json.loads(r)
 command=KUBE+['-n','immich-pilot','exec','deployment/immich-pet-tagger','--','python',remote+'/worker.py',remote,'--app','/app','--device','cpu','--weights',paths['yolo'],'--clip',paths['clip']]
else:
 command=[str(runtime/'venv/bin/python'),'-B',str(a.directory/'worker.py'),str(a.directory),'--app',(runtime/'upstream-app.txt').read_text().strip(),'--device','mps' if a.backend=='mac-mps' else 'cpu','--weights',str(runtime/'data/yolov8n.pt'),'--clip',str(runtime/'data/.cache/clip/ViT-B-16.pt')]
command+=['--label',a.label,'--threads',str(a.threads),'--pause',str(a.pause),'--inflight',str(a.inflight)]
if a.cpu_detector:command+=['--cpu-detector']
log=a.directory/(a.label+'.log');error=a.directory/(a.label+'.stderr')
print('START',a.label,flush=True)
observer=None
if a.backend.startswith('mac'):
 observation_log=(a.directory/(a.label+'-resource-summary.log')).open('w')
 observer=subprocess.Popen([str(runtime/'venv/bin/python'),str(Path(__file__).with_name('observe.py')),str(a.directory),'--label',a.label],stdout=observation_log,stderr=observation_log)

with log.open('w') as stdout,error.open('w') as stderr:
 worker=subprocess.Popen(command,stdout=stdout,stderr=stderr)
 sampled=False;last='';deadline=time.monotonic()+1200
 while worker.poll() is None:
  lines=log.read_text().splitlines()
  if lines and lines[-1]!=last:print(lines[-1],flush=True);last=lines[-1]
  if a.backend.startswith('mac') and not sampled and (a.directory/a.label/'rows.jsonl').exists():
   pid=(a.directory/a.label/'pid').read_text();sampled=True
   subprocess.Popen(['/usr/bin/sample',pid,'15','5','-file',str(a.directory/(a.label+'.sample.txt'))],stdout=stderr,stderr=stderr)
  if time.monotonic()>deadline:worker.terminate();raise RuntimeError('Diagnostic deadline exceeded')
  time.sleep(2)
 if worker.returncode:raise RuntimeError('Worker failed; inspect private stderr: '+str(error))
if a.backend=='still-fawn':
 archive=subprocess.check_output(KUBE+['-n','immich-pilot','exec','deployment/immich-pet-tagger','--','tar','czf','-','-C',remote,a.label],timeout=60)
 with tarfile.open(fileobj=io.BytesIO(archive),mode='r:gz') as tar:tar.extractall(a.directory,filter='data')
if observer:observer.wait(timeout=30)
print('COMPLETE',a.label,flush=True)
