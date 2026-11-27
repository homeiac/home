#!/usr/bin/env python3
"""Compare CPU/Metal extra capacity while permanent workers keep production running."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import logging
from pathlib import Path
import signal
import subprocess
import time
import experiment as evidence
from distributed import request

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
JOURNAL=ROOT/'docs/experiments/waffles/2026-11-26-continuous-production.jsonl'
spec=importlib.util.spec_from_file_location('capacity',HERE/'observe-capacity.py')
capacity=importlib.util.module_from_spec(spec);spec.loader.exec_module(capacity)
ADMITTED=('mac','pve','still-fawn','fun-bedbug')
owned=set()
initial_health=None
last_observed=0

def record(event,**values):
    evidence.JOURNAL=JOURNAL
    evidence.record(event,**values)

def totals(status):
    return {w:sum(r['jobs'] for r in status['runs'] if r['mode']=='production' and r['status']=='complete' and r['worker']==w) for w in ADMITTED}

def guard(force=False):
    global last_observed
    status=request('/admin/status')
    for name in ADMITTED:
        worker=next(w for w in status['workers'] if w['name']==name)
        if worker['base_instances']!=1:raise RuntimeError('Baseline unavailable: '+name)
    if force or time.monotonic()-last_observed>=15:
        observed=capacity.observe();last_observed=time.monotonic()
        record('resource_sample',observation=observed,production=totals(status),workers=status['workers'])
        if not observed['queue_healthy'] or observed['queue_health_seconds']>5:raise RuntimeError('Queue health guard')
        if observed['mac']['pressure']!=1:raise RuntimeError('Mac memory pressure guard')
        host=observed['still-fawn']
        if host['temperature_c'] is None or host['temperature_c']>=68:raise RuntimeError('Host thermal guard')
        if host['available_bytes']<512*1024**2:raise RuntimeError('Host memory guard')
        if initial_health:
            current=observed['other_pods']['healthy_restarts']
            for pod,restarts in initial_health.items():
                if pod not in current or current[pod]>restarts:raise RuntimeError('Previously healthy workload changed: '+pod)
    return status

def tune(worker,slots,device='cpu',cores=None):
    body={'worker':worker,'slots':slots,'mode':'benchmark','device':device,'note':'Continuous-production experiment; baseline unchanged'}
    if cores is not None:body['cpu_cores']=cores
    record('extra_policy_requested',**body);request('/admin/burst',body)
    deadline=time.monotonic()+360
    while True:
        status=guard()
        value=next(w for w in status['workers'] if w['name']==worker)
        if value['burst_instances']==slots and (not slots or value['burst_devices']==[device]) and (not slots or cores is None or value['burst_cpu_affinity']==[cores]):break
        if time.monotonic()>deadline:raise RuntimeError('Extra pool did not converge: '+worker)
        time.sleep(3)
    record('extra_policy_converged',**body)

def run(identifier,assets,workers):
    assert identifier.startswith('burst-')
    owned.add(identifier)
    request('/admin/run',{'id':identifier,'mode':'benchmark','workers':workers,'assets':assets})
    request('/admin/state',{'id':identifier,'state':'running'})
    deadline=time.monotonic()+900
    while True:
        status=guard()
        rows=[r for r in status['runs'] if r['id']==identifier]
        if any(r['status']=='failed' for r in rows):raise RuntimeError('Failed benchmark job')
        if sum(r['jobs'] for r in rows if r['status']=='complete')==len(assets):return evidence.database('jobs',identifier)
        if time.monotonic()>deadline:raise RuntimeError('Benchmark deadline exceeded')
        time.sleep(3)

def choose(trials):
    groups={}
    for trial in trials:
        key=(trial['worker'],trial['slots'],trial['device'],trial['cores'])
        groups.setdefault(key,[]).append(trial)
    candidates=[]
    for key,rows in groups.items():
        if len(rows)!=2 or not all(r['valid'] for r in rows):continue
        candidates.append(dict(zip(('worker','slots','device','cores'),key),photos_per_minute=60*sum(r['photos'] for r in rows)/sum(r['wall_seconds'] for r in rows),range=[min(r['photos_per_minute'] for r in rows),max(r['photos_per_minute'] for r in rows)]))
    if not candidates:raise RuntimeError('No valid repeated configuration')
    fastest=max(r['photos_per_minute'] for r in candidates)
    return min((r for r in candidates if r['photos_per_minute']>=fastest*.95),key=lambda r:(r['slots'],r['cores'] or 0)),candidates

def main():
    global initial_health
    logging.basicConfig(level=logging.INFO,format='%(message)s')
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('private_directory',type=Path)
    args=parser.parse_args();private=args.private_directory
    def interrupted(*_):raise KeyboardInterrupt('Continuous experiment interrupted')
    signal.signal(signal.SIGTERM,interrupted)
    truth=json.loads((private/'owner-confirmed-holdout.json').read_text())
    sample=json.loads((private/'distributed/benchmark.json').read_text())
    inventory=json.loads((private/'distributed/inventory.json').read_text())
    missing=set(truth['positive']+truth['negative'])-{a['id'] for a in sample}
    assets=sample+[a for a in inventory if a['id'] in missing]
    digest=hashlib.sha256('\n'.join(sorted(a['id'] for a in assets)).encode()).hexdigest()
    assert digest=='3beae47139538015c9968b5d39a38b5bfb3bdb1f9b740370406d6ca73ee57ca2'
    baseline={r['asset_id']:bool(r['result']['matches']) for r in evidence.database('jobs','tune-1127045925-mac-1-a')}
    assert set(baseline)=={a['id'] for a in assets}
    original=request('/api/burst')['workers']
    assert all(v['slots']==0 for v in original.values()),'Begin with extra pools drained'
    initial_health=capacity.observe()['other_pods']['healthy_restarts']
    session=datetime.now(timezone.utc).strftime('%m%d%H%M%S')
    plan=[('mac',n,d,None) for n in (1,3,5,7) for d in ('mps','cpu')]
    plan+=list(reversed(plan))
    sf_plan=[('still-fawn',2,'cpu',n) for n in (1,2,3,3,2,1)]
    record('protocol',session=session,sample_count=len(assets),sample_sha256=digest,
           classifier_sha256=hashlib.sha256((private/'distributed/classifier.json').read_bytes()).hexdigest(),
           runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
           git_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
           mac_plan=plan,still_fawn_plan=sf_plan,baseline_workers=list(ADMITTED),baseline_device='mps',
           user_preference='Compare CPU and Metal extra workers',production_start=totals(request('/admin/status')))
    trials=[];selected={};success=False
    def trial(worker,slots,device,cores,suffix):
        name=f'burst-{session}-{worker}-{device}-{slots}-c{cores or 0}-{suffix}'
        tune(worker,slots,device,cores)
        run(name+'-warm',assets[:max(6,slots*3)],[worker])
        before=guard(True);record('trial_started',run=name,worker=worker,slots=slots,device=device,cores=cores)
        rows=run(name,list(reversed(assets)) if suffix=='b' else assets,[worker])
        after=guard(True);summary,_=evidence.summarize(rows,truth,baseline)
        summary['unexpected_exit_delta']=sum(w['unexpected_exits'] for w in after['workers'])-sum(w['unexpected_exits'] for w in before['workers'])
        summary['valid'] &= summary['unexpected_exit_delta']==0
        summary['production_delta']={w:totals(after)[w]-totals(before)[w] for w in ADMITTED}
        result={'run':name,'worker':worker,'slots':slots,'device':device,'cores':cores,**summary}
        trials.append(result);record('trial_finished',**result)
        if not summary['valid']:raise RuntimeError('Quality or process stability gate failed')
    try:
        for index,(worker,slots,device,cores) in enumerate(plan):trial(worker,slots,device,cores,'a' if index<len(plan)//2 else 'b')
        selected['mac'],candidates=choose(trials);record('backend_selected',**selected['mac'],candidates=candidates)
        tune('mac',0)
        for index,(worker,slots,device,cores) in enumerate(sf_plan):trial(worker,slots,device,cores,'a' if index<len(sf_plan)//2 else 'b')
        selected['still-fawn'],candidates=choose([t for t in trials if t['worker']=='still-fawn']);record('backend_selected',**selected['still-fawn'],candidates=candidates)
        for profile,suffix in [('before','a'),('after','a'),('after','b'),('before','b')]:
            for worker in ('mac','still-fawn'):
                choice=selected[worker]
                tune(worker,1 if profile=='before' else choice['slots'],'mps' if profile=='before' and worker=='mac' else choice['device'],1 if profile=='before' and worker=='still-fawn' else choice['cores'])
            name=f'burst-{session}-pool-{profile}-{suffix}'
            run(name+'-warm',assets[:12],['mac','still-fawn'])
            before=guard(True)
            rows=run(name,list(reversed(assets)) if suffix=='b' else assets,['mac','still-fawn'])
            summary,_=evidence.summarize(rows,truth,baseline);after=guard(True)
            summary['unexpected_exit_delta']=sum(w['unexpected_exits'] for w in after['workers'])-sum(w['unexpected_exits'] for w in before['workers'])
            summary['valid'] &= summary['unexpected_exit_delta']==0
            summary['production_delta']={w:totals(after)[w]-totals(before)[w] for w in ADMITTED}
            trials.append({'run':name,**summary});record('trial_finished',run=name,**summary)
            if not summary['valid']:raise RuntimeError('Combined quality gate failed')
        success=True
    except BaseException as error:
        record('experiment_failed',error_type=type(error).__name__,reason=str(error));raise
    finally:
        actions=[('/admin/state',{'id':name,'state':'paused'},'benchmark_cleanup') for name in sorted(owned)]
        for worker in ('mac','still-fawn'):
            choice=selected.get(worker,{})
            body={'worker':worker,**original[worker],'note':'Restore extra pool after experiment'}
            if success:body.update(slots=choice['slots'],device=choice['device'],mode='production',**({'cpu_cores':choice['cores']} if choice['cores'] is not None else {}))
            actions.append(('/admin/burst',body,'final_extra_policy'))
        evidence.JOURNAL=JOURNAL;evidence.cleanup(actions)
    record('experiment_completed',selected=selected,production_end=totals(request('/admin/status')))
    (ROOT/'docs/reference/waffles-continuous-production.json').write_text(json.dumps({'selected':selected,'trials':trials},indent=2)+'\n')

if __name__=='__main__':main()
