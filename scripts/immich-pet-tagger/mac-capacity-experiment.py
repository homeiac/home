#!/usr/bin/env python3
"""Find sustainable Mac concurrency with repeated quality checks and a durable journal.

Permanent production baselines and other backend policies are never changed.
Only this controller's benchmark runs and Mac extra-worker policy are owned.
"""
import argparse
from datetime import datetime,timezone
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

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
spec=importlib.util.spec_from_file_location('continuous',HERE/'continuous-experiment.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
c.JOURNAL=ROOT/'docs/experiments/waffles/2026-11-26-fifo-capacity.jsonl'
c.memory_warning_policy='observe'
# Native hosts retain desired=1 and their existing independent safety guards.
c.required_baselines=('mac','pve','still-fawn')

def main():
    logging.basicConfig(level=logging.INFO,format='%(message)s')
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('private_directory',type=Path);args=p.parse_args()
    def interrupted(*_):raise KeyboardInterrupt('Mac capacity experiment interrupted')
    signal.signal(signal.SIGTERM,interrupted)
    private=args.private_directory
    truth=json.loads((private/'owner-confirmed-holdout.json').read_text())
    assets=json.loads((private/'distributed/benchmark.json').read_text())
    missing=set(truth['positive']+truth['negative'])-{a['id'] for a in assets}
    assets += [a for a in json.loads((private/'distributed/inventory.json').read_text()) if a['id'] in missing]
    digest=hashlib.sha256('\n'.join(sorted(a['id'] for a in assets)).encode()).hexdigest()
    assert digest=='3beae47139538015c9968b5d39a38b5bfb3bdb1f9b740370406d6ca73ee57ca2'
    reference={r['asset_id']:bool(r['result']['matches']) for r in evidence.database('jobs','tune-1127045925-mac-1-a')}
    assert set(reference)=={a['id'] for a in assets}
    original=request('/api/burst')['workers']['mac']
    c.initial_health=c.capacity.observe()['other_pods']['healthy_restarts']
    session=datetime.now(timezone.utc).strftime('%m%d%H%M%S')
    plan={'cpu':[2,4,8,12,15],'mps':[1,2,4,8]}
    c.record('protocol',session=session,plan=plan,cpu_threads=2,memory_warning_policy='observe',
             sample_sha256=digest,classifier_sha256=hashlib.sha256((private/'distributed/classifier.json').read_bytes()).hexdigest(),
             runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),git_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
             required_baselines=list(c.required_baselines),native_policy='Keep desired=1; observe independently guarded standby',original_policy=original,production_start=c.totals(request('/admin/status')))
    candidates=[];selected=None;adopted=False
    def pause_owned():
        for name in sorted(c.owned):request('/admin/state',{'id':name,'state':'paused'})
    def recover():
        pause_owned();request('/admin/burst',{'worker':'mac','slots':0,'mode':'production','note':'Drain rejected extra configuration; baseline stays running'})
        deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            status=request('/admin/status');mac=next(w for w in status['workers'] if w['name']=='mac')
            if mac['burst_instances']==0 and c.capacity.mac()['pressure']<4:return
            time.sleep(3)
        raise RuntimeError('Mac recovery did not complete')
    try:
        for device,levels in plan.items():
            regressions=0;previous=None
            for slots in levels:
                trials=[]
                try:
                    c.tune('mac',slots,device)
                    name=f'burst-{session}-fifo-{device}-{slots}'
                    c.run(name+'-warm',assets[:max(6,slots*2)],['mac'])
                    for suffix,sample in [('a',assets),('b',list(reversed(assets)))]:
                        before=c.guard(True);run=name+'-'+suffix;c.record('trial_started',run=run,device=device,slots=slots)
                        rows=c.run(run,sample,['mac']);after=c.guard(True)
                        summary,_=evidence.summarize(rows,truth,reference)
                        summary['unexpected_exit_delta']=sum(w['unexpected_exits'] for w in after['workers'] if w['name']=='mac')-sum(w['unexpected_exits'] for w in before['workers'] if w['name']=='mac')
                        summary['valid'] &= summary['unexpected_exit_delta']==0
                        summary['production_delta']={w:c.totals(after)[w]-c.totals(before)[w] for w in c.ADMITTED}
                        c.record('trial_finished',run=run,device=device,slots=slots,**summary);trials.append(summary)
                        if not summary['valid']:raise RuntimeError('Quality or process stability gate failed')
                    result={'device':device,'slots':slots,'cpu_threads':2,'photos_per_minute':60*sum(r['photos'] for r in trials)/sum(r['wall_seconds'] for r in trials),'trials':trials}
                    candidates.append(result);c.record('candidate_valid',**result)
                    regressions=regressions+1 if previous and result['photos_per_minute']<previous else 0
                    previous=result['photos_per_minute']
                    if regressions>=2:
                        c.record('device_escalation_stopped',device=device,slots=slots,reason='Two consecutive throughput regressions');break
                except RuntimeError as error:
                    c.record('configuration_rejected',device=device,slots=slots,reason=str(error))
                    if 'Baseline unavailable' in str(error) or 'Previously healthy workload' in str(error):raise
                    recover()
                    # Quality failure invalidates this configuration and all larger
                    # configurations on the same device; retain previous valid ones.
                    break
        if not candidates:raise RuntimeError('No repeated quality-valid configuration')
        selected=max(candidates,key=lambda r:r['photos_per_minute'])
        c.record('candidate_selected',**selected)
        pause_owned()
        request('/admin/burst',{'worker':'mac','slots':selected['slots'],'device':selected['device'],'cpu_threads':2,'mode':'production','note':'Adopt repeated quality-valid Mac FIFO capacity winner'})
        # Wait for process convergence, then observe real production, not canary speed.
        deadline=time.monotonic()+360
        while True:
            status=c.guard();mac=next(w for w in status['workers'] if w['name']=='mac')
            if mac['burst_instances']==selected['slots'] and mac['burst_devices']==[selected['device']]:break
            if time.monotonic()>deadline:raise RuntimeError('Selected production policy did not converge')
            time.sleep(3)
        before=c.guard(True);started=time.monotonic();c.record('adoption_started',selected=selected)
        while time.monotonic()-started<120:c.guard(True);time.sleep(10)
        after=c.guard(True);delta={w:c.totals(after)[w]-c.totals(before)[w] for w in c.ADMITTED}
        exits=sum(w['unexpected_exits'] for w in after['workers'] if w['name']=='mac')-sum(w['unexpected_exits'] for w in before['workers'] if w['name']=='mac')
        if any(delta[w]<=0 for w in c.required_baselines) or exits:raise RuntimeError('Production adoption continuity/stability failed')
        c.record('adoption_passed',seconds=time.monotonic()-started,production_delta=delta,unexpected_exit_delta=exits)
        adopted=True
    except BaseException as error:
        c.record('experiment_failed',error_type=type(error).__name__,reason=str(error));raise
    finally:
        actions=[('/admin/state',{'id':name,'state':'paused'},'benchmark_cleanup') for name in sorted(c.owned)]
        if not adopted:actions.append(('/admin/burst',{'worker':'mac',**original,'note':'Restore known production policy after capacity experiment'},'policy_restored'))
        evidence.JOURNAL=c.JOURNAL;evidence.cleanup(actions)
    c.record('experiment_completed',selected=selected,production_end=c.totals(request('/admin/status')))
    (ROOT/'docs/reference/waffles-mac-capacity.json').write_text(json.dumps({'selected':selected,'candidates':candidates},indent=2)+'\n')

if __name__=='__main__':main()
