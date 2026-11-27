#!/usr/bin/env python3
"""Observe adopted Mac production capacity without changing policies or stopping work."""
import argparse
import json
import time
import experiment
from distributed import request

p=argparse.ArgumentParser(description=__doc__);p.add_argument('--extras',type=int,required=True);p.add_argument('--seconds',type=int,default=60);args=p.parse_args()
experiment.JOURNAL=experiment.ROOT/'docs/experiments/waffles/2026-11-26-fifo-capacity.jsonl'
def totals(status):
    result={}
    for r in status['runs']:
        if r['mode']=='production' and r['status']=='complete':result[r['worker']]=result.get(r['worker'],0)+r['jobs']
    return result
start=time.monotonic();deadline=start+180
while True:
    status=request('/admin/status');mac=next(w for w in status['workers'] if w['name']=='mac')
    policy=request('/api/burst')['workers']['mac']
    if policy['slots']!=args.extras or policy['mode']!='production':raise RuntimeError('Production policy changed; observer will not override it')
    if mac['base_instances']==1 and mac['burst_instances']==args.extras:break
    if time.monotonic()>deadline:raise RuntimeError('Expected Mac processes did not converge')
    time.sleep(3)
before=totals(status);started=time.monotonic();exits=mac['unexpected_exits']
experiment.record('production_observation_started',policy=policy,workers=status['workers'],production=before)
while time.monotonic()-started<args.seconds:
    time.sleep(min(10,max(0,args.seconds-(time.monotonic()-started))))
    status=request('/admin/status');mac=next(w for w in status['workers'] if w['name']=='mac')
    if mac['base_instances']!=1 or mac['burst_instances']!=args.extras or mac['unexpected_exits']!=exits:
        experiment.record('production_observation_interrupted',worker=mac);raise RuntimeError('Mac capacity changed; see journal')
after=totals(status);elapsed=time.monotonic()-started;delta={w:after.get(w,0)-n for w,n in before.items()}
if delta.get('mac',0)<=0:raise RuntimeError('No committed Mac production progress')
result={'seconds':elapsed,'production_delta':delta,'mac_photos_per_minute':60*delta['mac']/elapsed,'policy':policy,'mac_instances':mac['active_instances']}
experiment.record('production_observation_passed',**result)
print(json.dumps(result,indent=2))
