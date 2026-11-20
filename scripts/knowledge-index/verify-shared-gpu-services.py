#!/usr/bin/env python3
"""Check actual Frigate detection and a bounded Ollama response around maintenance."""
import argparse
import json
import os
from pathlib import Path
import subprocess
p=argparse.ArgumentParser();p.add_argument('--generate',action='store_true');a=p.parse_args()
base=['kubectl','--kubeconfig',os.environ.get('KUBECONFIG',str(Path.home()/'kubeconfig'))]
def execute(ns,dep,args,data=None):
    r=subprocess.run(base+['-n',ns,'exec','-i','deployment/'+dep,'--']+args,input=data,text=True,capture_output=True,timeout=60)
    if r.returncode:raise RuntimeError(r.stderr[-1500:])
    return json.loads(r.stdout)
code="import urllib.request,json; f=json.load(urllib.request.urlopen('http://127.0.0.1:5000/api/stats',timeout=10)); print(json.dumps({'service':'frigate','uptime':f.get('service',{}).get('uptime'),'detectors':f.get('detectors'),'cameras':{k:{s:v.get(s) for s in ['camera_fps','process_fps','skipped_fps','detection_fps']} for k,v in f.get('cameras',{}).items()}}))"
print(json.dumps(execute('frigate','frigate',['python3','-c',code])),flush=True)
node="const r=await fetch('http://ollama-lb.ollama.svc.cluster.local/api/ps',{signal:AbortSignal.timeout(10000)});console.log(JSON.stringify(await r.json()));"
ps=execute('immich-pilot','immich-server',['node','--input-type=module','-e',node])
print(json.dumps({'service':'ollama','models':[{'name':m['name'],'size_vram':m.get('size_vram')} for m in ps['models']]}),flush=True)
if a.generate:
    if not ps['models']:raise RuntimeError('No loaded model; do not load an arbitrary model')
    name=ps['models'][0]['name']
    body={'model':name,'prompt':'Reply with the single word OK.','stream':False,'options':{'num_predict':8}}
    node="let input='';for await(const c of process.stdin)input+=c;const r=await fetch('http://ollama-lb.ollama.svc.cluster.local/api/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:input,signal:AbortSignal.timeout(45000)});console.log(JSON.stringify(await r.json()));"
    result=execute('immich-pilot','immich-server',['node','--input-type=module','-e',node],json.dumps(body))
    print(json.dumps({'service':'ollama_generation','model':name,'done':result.get('done'),'response':result.get('response'),'eval_count':result.get('eval_count')}))
