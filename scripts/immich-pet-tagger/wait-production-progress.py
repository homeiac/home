#!/usr/bin/env python3
"""Wait for every admitted baseline to complete work after a queue rollout."""
import time
from distributed import request

workers=('mac','pve','still-fawn','fun-bedbug')
def totals(status):
    return {w:sum(r['jobs'] for r in status['runs'] if r['mode']=='production' and r['status']=='complete' and r['worker']==w) for w in workers}

start=totals(request('/admin/status'));deadline=time.monotonic()+180
while True:
    status=request('/admin/status');current=totals(status)
    ready={w['name']:w['base_instances'] for w in status['workers']}
    if all(ready.get(w)==1 and current[w]>start[w] for w in workers):
        print('All admitted baselines progressing:',{w:current[w]-start[w] for w in workers})
        break
    if time.monotonic()>deadline:raise RuntimeError('Baseline progress not established after rollout')
    time.sleep(5)
