#!/usr/bin/env python3
"""Check decoder rollout, access boundary and aggregate runtime without private media IDs."""
import subprocess
from distributed import KUBE
print('START: checking media decoder rollout and access',flush=True)
subprocess.run(KUBE+['-n','immich-pilot','rollout','status','deployment/waffles-media','--timeout=120s'],check=True)
code='''const base='http://waffles-media.immich-pilot.svc.cluster.local:9201';
const health=await fetch(base+'/healthz',{signal:AbortSignal.timeout(10000)});
const unauthorized=await fetch(base+'/assets/00000000-0000-4000-8000-000000000000',{signal:AbortSignal.timeout(10000)});
if(health.status!==200||unauthorized.status!==401)throw Error('Decoder health/access check failed');
console.log('Decoder healthy; unauthenticated asset requests denied');'''
subprocess.run(KUBE+['-n','immich-pilot','exec','-i','deployment/waffles-queue','--','node','--input-type=module','-'],input=code,text=True,check=True)
subprocess.run(KUBE+['-n','immich-pilot','get','pods','-l','app=waffles-media'],check=True)
subprocess.run(KUBE+['-n','immich-pilot','logs','deployment/waffles-media','--tail=4'],check=True)
