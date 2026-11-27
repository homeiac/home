#!/usr/bin/env python3
"""Compare CPU threads in one extra model process, preserving all baseline workers."""
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
continuous=importlib.util.module_from_spec(spec);spec.loader.exec_module(continuous)
continuous.JOURNAL=ROOT/'docs/experiments/waffles/2026-11-26-cpu-threads.jsonl'
record=continuous.record

def tune(threads):
    request('/admin/burst',{'worker':'mac','slots':1,'mode':'benchmark','device':'cpu','cpu_threads':threads,'note':'Single model CPU-thread experiment; baseline Metal unchanged'})
    record('threads_requested',threads=threads)
    deadline=time.monotonic()+180
    while True:
        status=continuous.guard()
        worker=next(w for w in status['workers'] if w['name']=='mac')
        if worker['burst_instances']==1 and worker['burst_devices']==['cpu'] and worker['burst_threads']==[threads]:break
        if time.monotonic()>deadline:raise RuntimeError('CPU-thread configuration did not converge')
        time.sleep(3)
    record('threads_converged',threads=threads)

def main():
    logging.basicConfig(level=logging.INFO,format='%(message)s')
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('private_directory',type=Path)
    parser.add_argument('--allow-memory-warning',action='store_true',help='Record warning pressure; still stop on critical pressure or quality failure')
    args=parser.parse_args()
    continuous.memory_warning_policy='observe' if args.allow_memory_warning else 'stop'
    def interrupted(*_):raise KeyboardInterrupt('CPU-thread experiment interrupted')
    signal.signal(signal.SIGTERM,interrupted)
    private=args.private_directory
    truth=json.loads((private/'owner-confirmed-holdout.json').read_text())
    assets=json.loads((private/'distributed/benchmark.json').read_text())
    missing=set(truth['positive']+truth['negative'])-{a['id'] for a in assets}
    assets += [a for a in json.loads((private/'distributed/inventory.json').read_text()) if a['id'] in missing]
    digest=hashlib.sha256('\n'.join(sorted(a['id'] for a in assets)).encode()).hexdigest()
    assert digest=='3beae47139538015c9968b5d39a38b5bfb3bdb1f9b740370406d6ca73ee57ca2'
    baseline={r['asset_id']:bool(r['result']['matches']) for r in evidence.database('jobs','tune-1127045925-mac-1-a')}
    original=request('/api/burst')['workers']['mac']
    assert original['slots']<=1,'Thread experiment requires a single extra model'
    continuous.initial_health=continuous.capacity.observe()['other_pods']['healthy_restarts']
    session=datetime.now(timezone.utc).strftime('%m%d%H%M%S');plan=[2,4,8,16,16,8,4,2]
    record('protocol',memory_warning_policy=continuous.memory_warning_policy,session=session,plan=plan,extra_processes=1,device='cpu',baseline_device='mps',sample_sha256=digest,
           classifier_sha256=hashlib.sha256((private/'distributed/classifier.json').read_bytes()).hexdigest(),
           runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),git_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
           production_start=continuous.totals(request('/admin/status')),original_extra_policy=original)
    trials=[];selected=None
    try:
        for index,threads in enumerate(plan):
            suffix='a' if index<4 else 'b';name=f'burst-{session}-threads-{threads}-{suffix}'
            tune(threads);continuous.run(name+'-warm',assets[:6],['mac'])
            before=continuous.guard(True);record('trial_started',run=name,threads=threads)
            rows=continuous.run(name,assets if suffix=='a' else list(reversed(assets)),['mac'])
            after=continuous.guard(True);summary,_=evidence.summarize(rows,truth,baseline)
            summary['unexpected_exit_delta']=sum(w['unexpected_exits'] for w in after['workers'])-sum(w['unexpected_exits'] for w in before['workers'])
            summary['valid'] &= summary['unexpected_exit_delta']==0
            summary['production_delta']={w:continuous.totals(after)[w]-continuous.totals(before)[w] for w in continuous.ADMITTED}
            result={'run':name,'threads':threads,**summary};trials.append(result);record('trial_finished',**result)
            if not summary['valid']:raise RuntimeError('Thread trial failed quality gate')
        candidates=[]
        for threads in sorted(set(plan)):
            rows=[r for r in trials if r['threads']==threads]
            if len(rows)==2 and all(r['valid'] for r in rows):candidates.append({'threads':threads,'photos_per_minute':60*sum(r['photos'] for r in rows)/sum(r['wall_seconds'] for r in rows),'range':[min(r['photos_per_minute'] for r in rows),max(r['photos_per_minute'] for r in rows)]})
        fastest=max(c['photos_per_minute'] for c in candidates)
        selected=min((c for c in candidates if c['photos_per_minute']>=fastest*.95),key=lambda c:c['threads'])
        record('threads_selected',selected=selected,candidates=candidates)
    except BaseException as error:
        record('experiment_failed',error_type=type(error).__name__,reason=str(error));raise
    finally:
        evidence.JOURNAL=continuous.JOURNAL
        actions=[('/admin/state',{'id':name,'state':'paused'},'benchmark_cleanup') for name in sorted(continuous.owned)]
        policy={**original,'worker':'mac','note':'Restore CPU-thread experiment settings'}
        if selected:policy.update(slots=1,device='cpu',cpu_threads=selected['threads'],mode='production',note='Selected repeated quality-valid CPU-thread configuration')
        actions.append(('/admin/burst',policy,'final_extra_policy'));evidence.cleanup(actions)
    record('experiment_completed',selected=selected,production_end=continuous.totals(request('/admin/status')))
    (ROOT/'docs/reference/waffles-cpu-threads.json').write_text(json.dumps({'selected':selected,'trials':trials},indent=2)+'\n')

if __name__=='__main__':main()
