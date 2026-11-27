#!/usr/bin/env python3
"""Adopt independently validated still-fawn capacity, with bounded observation.

This is an operational decision, not completion of the interrupted combined
experiment. Mac extras stay drained. All observations and restoration are kept.
"""
from datetime import datetime,timezone
import importlib.util
import json
from pathlib import Path
import time
from distributed import request

here=Path(__file__).resolve().parent;root=here.parents[1]
spec=importlib.util.spec_from_file_location('continuous',here/'continuous-experiment.py')
continuous=importlib.util.module_from_spec(spec);spec.loader.exec_module(continuous)
continuous.JOURNAL=root/'docs/experiments/waffles/2026-11-26-still-fawn-adoption.jsonl'
rows=[json.loads(l) for l in (root/'docs/experiments/waffles/2026-11-26-continuous-production.jsonl').read_text().splitlines()]
evidence=[r for r in rows if r.get('run') in ('burst-1127054343-still-fawn-cpu-2-c3-a','burst-1127054343-still-fawn-cpu-2-c3-b') and r['event']=='trial_finished']
assert len(evidence)==2 and all(r['valid'] and r['accuracy']=={'true_positive':9,'false_positive':0} and r['decisions_changed']==0 for r in evidence)
original=request('/api/burst')['workers'];assert original['mac']['slots']==0
before=request('/admin/status');health=continuous.capacity.observe();initial=health['other_pods']['healthy_restarts']
exits={w['name']:w['unexpected_exits'] for w in before['workers']}
continuous.record('adoption_plan',at_utc=datetime.now(timezone.utc).isoformat(),
  basis=[r['run'] for r in evidence],settings={'slots':2,'cpu_cores':3,'device':'cpu','mode':'production'},
  observation_seconds=120,combined_experiment_complete=False,production_start=continuous.totals(before))

def check(status,observed):
    assert all(next(w['base_instances'] for w in status['workers'] if w['name']==name)==1 for name in continuous.ADMITTED),'Baseline unavailable'
    host=observed['still-fawn']
    assert host['temperature_c'] is not None and host['temperature_c']<68 and host['available_bytes']>=512*1024**2,'still-fawn capacity guard'
    assert observed['queue_healthy'] and observed['queue_health_seconds']<5,'Queue health'
    assert all(observed['other_pods']['healthy_restarts'].get(pod)==n for pod,n in initial.items()),'Other workload health changed'
    assert all(w['unexpected_exits']==exits[w['name']] for w in status['workers']),'Unexpected worker exit'

check(before,health);success=False
try:
    request('/admin/burst',{'worker':'still-fawn','slots':2,'cpu_cores':3,'device':'cpu','mode':'production','note':'Independent two-pass quality-valid SF capacity; combined study remains incomplete'})
    deadline=time.monotonic()+180;converged=None
    while True:
        status=request('/admin/status');observed=continuous.capacity.observe()
        continuous.record('production_observation',observation=observed,production=continuous.totals(status),workers=status['workers'])
        check(status,observed)
        active=next(w for w in status['workers'] if w['name']=='still-fawn')
        if active['burst_instances']==2 and active['burst_cpu_affinity']==[3]:
            if converged is None:converged=time.monotonic();continuous.record('capacity_converged')
            if time.monotonic()-converged>=120:
                assert all(continuous.totals(status)[w]>continuous.totals(before)[w] for w in continuous.ADMITTED),'Production did not advance'
                success=True;continuous.record('adoption_completed',production_end=continuous.totals(status));break
        elif converged is not None:raise RuntimeError('Extra capacity lost after convergence')
        if converged is None and time.monotonic()>deadline:raise RuntimeError('Capacity did not converge')
        time.sleep(15)
finally:
    if not success:
        request('/admin/burst',{'worker':'still-fawn',**original['still-fawn'],'note':'Restore unsuccessful SF adoption'})
        continuous.record('adoption_restored',reason='Observation did not complete; previous extra policy restored')
