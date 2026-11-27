#!/usr/bin/env python3
"""Matched-byte, one-process YOLO/CLIP benchmark; no queue claims or Immich writes.

Cold load and six warmups excluded. Two reversed passes, exact image hashes,
per-stage wall timings, actual thread counts and all-thread stack samples are retained.
"""
import argparse,os,json,time,hashlib,sys,logging,platform,resource,threading
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);p.add_argument('--device',choices=['cpu','mps'],required=True);p.add_argument('--threads',type=int,default=2);p.add_argument('--app',required=True);p.add_argument('--weights',required=True);p.add_argument('--clip',required=True);p.add_argument('--label',required=True);p.add_argument('--pause',type=int,default=0);p.add_argument('--inflight',type=int,default=1);p.add_argument('--cpu-detector',action='store_true');a=p.parse_args()
os.umask(0o077);a.directory=a.directory.resolve();out=a.directory/a.label;out.mkdir(exist_ok=False)
for k in ['OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS']:os.environ[k]=str(a.threads)
os.environ.update(MODEL_WORKERS='1',SCAN_WORKERS='1',YOLO_MODEL_NAME=a.weights,CLIP_PRETRAINED='openai',YOLO_CONFIG_DIR=str(out/'yolo'))
sys.path.insert(0,a.app)
import torch,numpy as np
import ultralytics.utils.torch_utils as yt
yt.NUM_THREADS=a.threads;torch.set_num_threads(a.threads)
import device
device.pick_device=lambda:a.device
import embedder,detector,inference,classifier
if a.cpu_detector:detector.pick_device=lambda:'cpu'
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
logging.basicConfig(level=logging.WARNING)
config=json.loads((a.directory/'classifier.json').read_text());scaler=StandardScaler();model=LogisticRegression()
for obj,values in [(scaler,config['scaler']),(model,config['model'])]:
 for k,v in values.items():setattr(obj,k,np.asarray(v) if isinstance(v,list) else v)
manifest=json.loads((a.directory/'manifest.json').read_text())
from PIL import Image
for row in manifest:assert hashlib.sha256((a.directory/row['file']).read_bytes()).hexdigest()==row['sha256']
def snapshot():
 r={'wall':time.time(),'cpu':time.process_time(),'rss':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
 for file in ['/sys/fs/cgroup/cpu.stat','/sys/fs/cgroup/cpu.max','/proc/pressure/cpu','/proc/pressure/memory','/proc/pressure/io','/sys/fs/cgroup/memory.events']:
  if Path(file).exists():r[file]=Path(file).read_text()
 return r
# Non-intrusive Python stack sampling covers caller and actual model threads.
from collections import Counter
samples=Counter();sampling_stop=threading.Event()
def sample_stacks():
 while not sampling_stop.wait(.01):
  names={t.ident:t.name for t in threading.enumerate()}
  for ident,frame in sys._current_frames().items():
   if ident==threading.get_ident():continue
   stack=[]
   while frame:
    stack.append(f'{Path(frame.f_code.co_filename).name}:{frame.f_code.co_name}:{frame.f_lineno}');frame=frame.f_back
   samples[(names.get(ident,str(ident)),tuple(stack))]+=1
import importlib.metadata
meta={'versions':{name:importlib.metadata.version(name) for name in ['torch','torchvision','open_clip_torch','ultralytics','scikit-learn','Pillow']},'source_hashes':{name:hashlib.sha256((Path(a.app)/(name+'.py')).read_bytes()).hexdigest() for name in ['embedder','detector','classifier','device']},'pid':os.getpid(),'label':a.label,'device':a.device,'threads_requested':a.threads,'inflight':a.inflight,'cpu_detector':a.cpu_detector,'platform':platform.platform(),'torch':torch.__version__,'numpy':np.__version__,'classifier_sha256':hashlib.sha256((a.directory/'classifier.json').read_bytes()).hexdigest(),'manifest_sha256':hashlib.sha256((a.directory/'manifest.json').read_bytes()).hexdigest(),'weights_sha256':hashlib.sha256(Path(a.weights).read_bytes()).hexdigest(),'clip_sha256':hashlib.sha256(Path(a.clip).read_bytes()).hexdigest()}
# Observe actual model-thread settings and device placement, without changing math.
import open_clip
from ultralytics import YOLO
original_create=open_clip.create_model_and_transforms
original_yolo_call=YOLO.__call__
def create_observed(*args,**kwargs):
 kwargs.setdefault('cache_dir',str(Path(a.clip).parent))
 result=original_create(*args,**kwargs);clip_model=result[0];original_encode=clip_model.encode_image
 def encode_observed(*args,**kwargs):
  meta['clip_actual_threads']=torch.get_num_threads()
  meta['clip_parameter_device']=str(next(clip_model.parameters()).device)
  return original_encode(*args,**kwargs)
 clip_model.encode_image=encode_observed
 return result
def yolo_observed(self,*args,**kwargs):
 result=original_yolo_call(self,*args,**kwargs)
 meta['yolo_actual_threads']=torch.get_num_threads()
 meta['yolo_parameter_device']=str(next(self.model.parameters()).device)
 return result
open_clip.create_model_and_transforms=create_observed
YOLO.__call__=yolo_observed
(out/'pid').write_text(str(os.getpid()));(out/'metadata.json').write_text(json.dumps(meta,indent=2))
def process(row,pass_id):
 start=time.perf_counter();path=a.directory/row['file'];image=Image.open(path).convert('RGB');decoded=time.perf_counter()
 before=inference.model_error_count();crops=embedder.crop_animals(image,conf=.25) or [(None,image)];detected=time.perf_counter();pred=[];embedding=classification=0
 for box,crop in crops:
  t=time.perf_counter();vector=embedder.embed_image(crop);embedding+=time.perf_counter()-t
  assert vector is not None and inference.model_error_count()==before
  t=time.perf_counter();name,score=classifier.classify(vector,config['names'],model,scaler);classification+=time.perf_counter()-t
  pred.append({'name':name,'score':float(score),'box':list(box) if box else None,'accepted':name=='Waffles' and box is not None and score>=.90})
 end=time.perf_counter()
 return {'index':row['index'],'expected':row['expected'],'pass':pass_id,'decode':decoded-start,'detect':detected-decoded,'embed':embedding,'classify':classification,'total':end-start,'predictions':pred,'matched':any(x['accepted'] for x in pred),'torch_threads_main':torch.get_num_threads()}
print(json.dumps({'event':'loading','label':a.label,'pid':os.getpid()}),flush=True)
load=time.monotonic()
with inference.inference_session():
 meta['load_seconds']=time.monotonic()-load
 for row in manifest[:6]:process(row,'warmup')
 (out/'ready').touch();print(json.dumps({'event':'ready','label':a.label,'pid':os.getpid(),'pause':a.pause}),flush=True)
 if a.label=='mac-mps-traced':
  print('Waiting up to 300 seconds for owner sudo capture to start',flush=True)
  deadline=time.monotonic()+300
  while not (out/'trace-started').exists():
   if time.monotonic()>deadline:raise RuntimeError('Privileged capture not started; no silent untraced replacement')
   time.sleep(1)
 time.sleep(a.pause)
 before=snapshot();sampler=threading.Thread(target=sample_stacks,daemon=True);sampler.start();rows=[]
 try:
  from concurrent.futures import ThreadPoolExecutor
  meta['pass_wall_seconds']=[]
  for n,items in enumerate([manifest,list(reversed(manifest))]):
   pass_start=time.perf_counter()
   from contextlib import nullcontext
   with (ThreadPoolExecutor(max_workers=a.inflight) if a.inflight>1 else nullcontext()) as pool:
    results=pool.map(lambda row:process(row,n),items) if pool else map(lambda row:process(row,n),items)
    for r in results:
     rows.append(r)
     with (out/'rows.jsonl').open('a') as f:f.write(json.dumps(r)+'\n')
     print(json.dumps({'event':'progress','label':a.label,'done':len(rows),'total':len(manifest)*2}),flush=True)
   meta['pass_wall_seconds'].append(time.perf_counter()-pass_start)
 finally:
  sampling_stop.set();sampler.join(timeout=2)
  (out/'python-stacks.json').write_text(json.dumps([{'thread':key[0],'stack':list(key[1]),'samples':count} for key,count in samples.items()],indent=2))
 meta.update(before=before,after=snapshot(),clip_avg_batch=embedder.get_avg_batch_size(),yolo_avg_batch=detector.yolo_batch_total/max(1,detector.yolo_batch_count))
(out/'metadata.json').write_text(json.dumps(meta,indent=2)+'\n')
print(json.dumps({'event':'complete','label':a.label,'rows':len(rows)}),flush=True)
