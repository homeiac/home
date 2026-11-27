#!/usr/bin/env python3
"""Journal a counterbalanced live-concurrency sweep with quality and rollback gates."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import statistics
import signal
import subprocess
import time
import urllib.parse
from distributed import KUBE, request

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
JOURNAL=ROOT/'docs/experiments/waffles/2026-11-26-live-tuning.jsonl'
OWNED_RUNS=set()


def record(event, **values):
    item={'at':datetime.now(timezone.utc).isoformat(),'event':event,**values}
    JOURNAL.parent.mkdir(parents=True,exist_ok=True)
    with JOURNAL.open('a') as stream:
        stream.write(json.dumps(item,sort_keys=True)+'\n');stream.flush();os.fsync(stream.fileno())
    logging.info('%s',json.dumps(item))


def database(operation, identifier=''):
    code='''import {createRequire} from 'node:module';
const {Client}=createRequire('/usr/src/app/server/package.json')('pg');const db=new Client();await db.connect();
const sql=process.argv[2]==='runs'?'SELECT id,mode,state,workers FROM waffles.runs':
 `SELECT j.asset_id,j.worker,j.status,j.result,j.processing_seconds,j.attempts,j.completed_at,r.started_at FROM waffles.jobs j JOIN waffles.runs r ON r.id=j.run_id WHERE j.run_id=$1 ORDER BY j.ordinal`;
console.log(JSON.stringify((await db.query(sql,process.argv[2]==='runs'?[]:[process.argv[3]])).rows));await db.end();'''
    output=subprocess.run(KUBE+['-n','immich-pilot','exec','-i','deployment/waffles-queue','--','node','--input-type=module','-',operation,identifier],input=code,text=True,capture_output=True,check=True)
    return json.loads(output.stdout)


def snapshot():
    data=request('/admin/status')
    queries={
        'k8s_cpu_cores':'sum by(pod)(rate(container_cpu_usage_seconds_total{namespace="immich-pilot",container="worker",pod=~"waffles-worker-.*"}[1m]))',
        'k8s_working_set_bytes':'sum by(pod)(container_memory_working_set_bytes{namespace="immich-pilot",container="worker",pod=~"waffles-worker-.*"})',
        'k8s_restarts':'sum(kube_pod_container_status_restarts_total{namespace="immich-pilot",pod=~"waffles-worker-.*"})'}
    metrics={}
    for name,query in queries.items():
        path='/api/v1/namespaces/monitoring/services/http:kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?'+urllib.parse.urlencode({'query':query})
        raw=json.loads(subprocess.check_output(KUBE+['get','--raw',path],text=True))
        metrics[name]=[{'labels':r['metric'],'value':r['value'][1]} for r in raw['data']['result']]
    return {'workers':data['workers'],'metrics':metrics,'tuning':request('/api/tuning')['workers']}


def tune(worker,slots,note):
    record('tuning_requested',worker=worker,slots=slots,note=note)
    request('/admin/tuning',{'worker':worker,'slots':slots,'note':note})
    deadline=time.monotonic()+240
    while True:
        workers=request('/admin/status')['workers']
        active=next((w.get('active_instances',0) for w in workers if w['name']==worker),0)
        if active==slots:break
        if time.monotonic()>deadline:raise RuntimeError(f'{worker} did not converge to {slots} ready processes')
        time.sleep(5)
    record('tuning_converged',worker=worker,slots=slots)


def sample_run(identifier,assets,workers):
    OWNED_RUNS.add(identifier)
    existing=[r for r in request('/admin/status')['runs'] if r['id']==identifier]
    if not existing:
        request('/admin/run',{'id':identifier,'mode':'benchmark','workers':workers,'assets':assets})
    request('/admin/state',{'id':identifier,'state':'running'})
    deadline=time.monotonic()+900
    while True:
        rows=[r for r in request('/admin/status')['runs'] if r['id']==identifier]
        done=sum(r['jobs'] for r in rows if r['status']=='complete')
        if any(r['status']=='failed' for r in rows):raise RuntimeError('Failed benchmark jobs')
        if done==len(assets):return database('jobs',identifier)
        if time.monotonic()>deadline:raise RuntimeError('Benchmark deadline exceeded')
        time.sleep(5)


def summarize(rows,truth,baseline):
    predictions={r['asset_id']:bool(r['result']['matches']) for r in rows}
    elapsed=(max(datetime.fromisoformat(r['completed_at']) for r in rows)-datetime.fromisoformat(rows[0]['started_at'])).total_seconds()
    seconds=sorted(r['processing_seconds'] for r in rows)
    accuracy={'true_positive':sum(predictions[a] for a in truth['positive']),
              'false_positive':sum(predictions[a] for a in truth['negative'])}
    differences=sum(predictions[k]!=v for k,v in baseline.items()) if baseline else 0
    valid=accuracy['true_positive']>=9 and accuracy['false_positive']==0 and differences==0 and max(r['attempts'] for r in rows)==1
    return {'valid':valid,'photos':len(rows),'wall_seconds':elapsed,'photos_per_minute':60*len(rows)/elapsed,
            'mean_processing_seconds':statistics.mean(seconds),'p50_seconds':statistics.median(seconds),
            'p95_seconds':seconds[int(.95*(len(seconds)-1))],'accuracy':accuracy,'decisions_changed':differences,
            'max_attempts':max(r['attempts'] for r in rows),
            'backend_counts':{w:sum(r['worker']==w for r in rows) for w in sorted({r['worker'] for r in rows})}},predictions


def resource_gate(summary,before,after):
    """Reject measurements spanning an inference-process exit or pod restart."""
    exits=lambda s:sum(w.get('unexpected_exits',0) for w in s['workers'])
    restarts=lambda s:sum(float(r['value']) for r in s['metrics']['k8s_restarts'])
    summary['unexpected_exit_delta']=exits(after)-exits(before)
    summary['k8s_restart_delta']=restarts(after)-restarts(before)
    summary['valid'] &= summary['unexpected_exit_delta']==0 and summary['k8s_restart_delta']==0


def cleanup(actions):
    """Attempt every restoration independently; never hide a failed resume."""
    failed=[]
    for path,body,event in actions:
        for attempt in range(3):
            try:
                request(path,body);record(event,**body);break
            except Exception as error:
                if attempt==2:
                    failed.append(body);record('restoration_failed',action=event,error_type=type(error).__name__,**body)
                else:time.sleep(3)
    if failed:raise RuntimeError('Experiment restoration incomplete; inspect journal and restore recorded production runs')


def main():
    logging.basicConfig(level=logging.INFO,format='%(message)s')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('private_directory',type=Path)
    parser.add_argument('--prepare-only',action='store_true')
    args=parser.parse_args();private=args.private_directory
    def interrupted(*_):raise KeyboardInterrupt('Experiment interrupted')
    signal.signal(signal.SIGTERM,interrupted)
    truth=json.loads((private/'owner-confirmed-holdout.json').read_text())
    inventory=json.loads((private/'distributed/inventory.json').read_text())
    sample=json.loads((private/'distributed/benchmark.json').read_text())
    ids={a['id'] for a in sample};holdout=set(truth['positive']+truth['negative'])
    assets=sample+[a for a in inventory if a['id'] in holdout-ids]
    assert holdout <= {a['id'] for a in assets},'Holdout inventory incomplete'
    session=datetime.now(timezone.utc).strftime('%m%d%H%M%S')
    digest=hashlib.sha256('\n'.join(sorted(a['id'] for a in assets)).encode()).hexdigest()
    record('protocol',sample_count=len(assets),sample_sha256=digest,
           classifier_sha256=hashlib.sha256((private/'distributed/classifier.json').read_bytes()).hexdigest(),
           plan={'mac':[1,2,4,4,2,1],'still-fawn':[1,2,2,1]},quality_gate='same decisions; at least 9/13 positive; 0/13 false positive; one attempt per job; no unplanned exits or restarts',selection_tolerance_percent=5,
           phase='preparation' if args.prepare_only else 'execution',git_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip())
    if args.prepare_only:return
    original=request('/api/tuning')['workers']
    runs=[r for r in database('runs') if r['mode']=='production' and r['state']=='running']
    selected={w:original[w]['slots'] for w in ('mac','still-fawn')}
    results=[];baseline=None;success=False
    try:
        for run in runs:
            request('/admin/state',{'id':run['id'],'state':'paused'});record('production_paused',run=run['id'])
        deadline=time.monotonic()+120
        while any(r['status']=='running' and r['mode']=='production' for r in request('/admin/status')['runs']):
            if time.monotonic()>deadline:raise RuntimeError('Production claims did not drain')
            time.sleep(3)
        for worker,plan in [('mac',[1,2,4,4,2,1]),('still-fawn',[1,2,2,1])]:
            invalid=set()
            for index,slots in enumerate(plan):
                if slots in invalid:
                    record('trial_skipped',worker=worker,slots=slots,reason='Earlier quality/resource failure for this configuration');continue
                suffix='a' if index<len(plan)//2 else 'b'
                identifier=f'tune-{session}-{worker}-{slots}-{suffix}'
                try:
                    tune(worker,slots,identifier)
                    await_warm=assets[:max(3,slots*3)]
                    sample_run(identifier+'-warm',await_warm,[worker])
                    before=snapshot();record('trial_started',run=identifier,worker=worker,slots=slots,reverse=suffix=='b',resource_snapshot=before)
                    rows=sample_run(identifier,list(reversed(assets)) if suffix=='b' else assets,[worker])
                    after=snapshot();summary,predictions=summarize(rows,truth,baseline)
                    resource_gate(summary,before,after)
                    record('trial_finished',run=identifier,worker=worker,slots=slots,resource_snapshot=after,**summary)
                    results.append({'run':identifier,'worker':worker,'slots':slots,**summary})
                    if baseline is None:
                        if not summary['valid']:raise RuntimeError('Baseline failed quality gate')
                        baseline=predictions
                    if not summary['valid']:
                        invalid.add(slots);tune(worker,1,'quality/resource rollback')
                except Exception as error:
                    cleanup([('/admin/state',{'id':run,'state':'paused'},'trial_paused') for run in OWNED_RUNS if run.startswith(identifier)])
                    record('trial_failed',run=identifier,worker=worker,slots=slots,error_type=type(error).__name__,reason=str(error))
                    invalid.add(slots);tune(worker,1,'failed trial rollback')
                    if slots==1:raise
            candidates=[]
            for slots in sorted(set(plan)):
                rows=[r for r in results if r['worker']==worker and r['slots']==slots and r['valid']]
                if len(rows)!=2:continue
                pace=60*sum(r['photos'] for r in rows)/sum(r['wall_seconds'] for r in rows)
                spread=max(r['photos_per_minute'] for r in rows)/min(r['photos_per_minute'] for r in rows)-1
                candidates.append({'slots':slots,'photos_per_minute':pace,'repeat_spread':spread})
            if not candidates:raise RuntimeError('No valid repeated configuration')
            fastest=max(c['photos_per_minute'] for c in candidates)
            selected[worker]=min(c['slots'] for c in candidates if c['photos_per_minute']>=fastest*.95)
            record('backend_selected',worker=worker,slots=selected[worker],candidates=candidates)
            tune(worker,selected[worker],'selected measured configuration')
        # Combined ABBA comparison, with unchanged PVE and the same exact inputs.
        for profile,suffix in [('before','a'),('after','a'),('after','b'),('before','b')]:
            for worker in selected:tune(worker,1 if profile=='before' else selected[worker],f'combined {profile}-{suffix}')
            name=f'tune-{session}-pool-{profile}-{suffix}'
            sample_run(name+'-warm',assets[:12],['mac','pve','still-fawn'])
            before=snapshot();record('trial_started',run=name,resource_snapshot=before)
            rows=sample_run(name,list(reversed(assets)) if suffix=='b' else assets,['mac','pve','still-fawn'])
            summary,_=summarize(rows,truth,baseline);after=snapshot()
            resource_gate(summary,before,after)
            record('trial_finished',run=name,resource_snapshot=after,**summary)
            results.append({'run':name,**summary})
            if not summary['valid']:raise RuntimeError('Combined quality gate failed')
        success=True
    finally:
        actions=[('/admin/state',{'id':run,'state':'paused'},'trial_cleanup') for run in sorted(OWNED_RUNS)]
        for worker in selected:
            slots=selected[worker] if success else original[worker]['slots']
            actions.append(('/admin/tuning',{'worker':worker,'slots':slots,'note':'experiment final selection' if success else 'experiment rollback'},'final_tuning'))
        for run in runs:
            actions.append(('/admin/state',{'id':run['id'],'state':'running'},'production_resumed'))
        cleanup(actions)
    report={'selected':selected,'sample_count':len(assets),'sample_sha256':digest,'trials':results}
    (ROOT/'docs/reference/waffles-live-tuning.json').write_text(json.dumps(report,indent=2)+'\n')
    record('experiment_completed',selected=selected,valid_trials=sum(r['valid'] for r in results))


if __name__=='__main__':main()
