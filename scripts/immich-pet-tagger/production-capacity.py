#!/usr/bin/env python3
"""Raise Mac production capacity first, measure real work, retain it unless worse.

No benchmark mode or run-state mutations. Same CPU device, two inference threads,
classifier and thresholds. Extra counts change only. Concurrent quality evidence
above eight extras is not claimed; this is an operational capacity experiment.
"""
import argparse
from datetime import datetime,timezone
import importlib.util
import json
import hashlib
import subprocess
import logging
from pathlib import Path
import signal
import time
import experiment
from distributed import request

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('capacity',HERE/'observe-capacity.py')
capacity=importlib.util.module_from_spec(spec);spec.loader.exec_module(capacity)
experiment.JOURNAL=experiment.ROOT/'docs/experiments/waffles/2026-11-26-fifo-capacity.jsonl'

def mac(status):return next(w for w in status['workers'] if w['name']=='mac')
def totals(status):
    return sum(r['jobs'] for r in status['runs'] if r['mode']=='production' and r['status']=='complete' and r['worker']=='mac')
def tune(slots,note):
    body={'worker':'mac','slots':slots,'mode':'production','device':'cpu','cpu_threads':2,'note':note}
    request('/admin/burst',body);experiment.record('production_capacity_requested',**body)

def main():
    logging.basicConfig(level=logging.INFO,format='%(message)s')
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--levels',nargs='+',type=int,default=[12,15]);p.add_argument('--window-seconds',type=int,default=60);args=p.parse_args()
    original=request('/api/burst')['workers']['mac']
    assert original['mode']=='production' and original['device']=='cpu' and original['cpu_threads']==2
    assert args.window_seconds>=30 and all(original['slots']<n<=15 for n in args.levels) and args.levels==sorted(set(args.levels))
    last_good=original['slots'];current=last_good;best=None;starting_exits=mac(request('/admin/status'))['unexpected_exits']
    def interrupt(*_):raise KeyboardInterrupt('Owner interrupted measurement; retain current production policy')
    signal.signal(signal.SIGTERM,interrupt)
    def guard():
        status=request('/admin/status');worker=mac(status);observation=capacity.mac()
        experiment.record('production_capacity_sample',worker=worker,mac=observation,production=totals(status))
        if worker['base_instances']!=1:raise RuntimeError('Mac permanent baseline unavailable')
        if worker['unexpected_exits']>starting_exits:raise RuntimeError('Mac process crash')
        if observation['pressure']>=4:raise RuntimeError('Mac critical memory pressure')
        policy=request('/api/burst')['workers']['mac']
        if policy['slots']!=current or policy['mode']!='production':raise KeyboardInterrupt('External policy change; do not override')
        return status
    def measure(slots):
        deadline=time.monotonic()+360
        while True:
            status=guard()
            if mac(status)['burst_instances']==slots:break
            if time.monotonic()>deadline:raise RuntimeError('Production workers failed to converge')
            time.sleep(5)
        windows=[]
        for index in range(2):
            before=totals(guard());started=time.monotonic()
            while time.monotonic()-started<args.window_seconds:
                time.sleep(min(10,max(0,args.window_seconds-(time.monotonic()-started))));status=guard()
                if mac(status)['burst_instances']!=slots:raise RuntimeError('Production process count dropped')
            elapsed=time.monotonic()-started;done=totals(status)-before
            rate=60*done/elapsed;windows.append(rate)
            experiment.record('production_capacity_window',extras=slots,window=index+1,seconds=elapsed,completed=done,photos_per_minute=rate)
        return sum(windows)/len(windows),windows
    experiment.record('production_capacity_protocol',at_start=datetime.now(timezone.utc).isoformat(),floor_extras=last_good,levels=args.levels,window_seconds=args.window_seconds,
                      runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),git_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=experiment.ROOT,text=True).strip(),rule='Raise production first. Two windows; retain unless both below 90% of preceding accepted rate, crash, critical pressure or lost worker. No benchmark diversion.',quality_scope='Same previously validated CPU model and two-thread configuration; no new labeled accuracy claim for higher concurrency.')
    try:
        # Reuse a fresh completed production observation instead of repeating it.
        observations=[json.loads(line) for line in experiment.JOURNAL.read_text().splitlines()]
        reference=next((r for r in reversed(observations) if r['event']=='production_observation_passed'
                       and r['policy']['slots']==last_good and r['policy']['mode']=='production'
                       and (datetime.now(timezone.utc)-datetime.fromisoformat(r['at'])).total_seconds()<300),None)
        if reference:
            best=reference['mac_photos_per_minute'];experiment.record('production_capacity_reference_reused',reference_at=reference['at'],photos_per_minute=best)
        else:best,_=measure(last_good)
        for slots in args.levels:
            current=slots;tune(current,'Raise production baseline before measuring; preserve throughput while experimenting')
            rate,windows=measure(current)
            if all(r<best*.9 for r in windows):
                experiment.record('production_capacity_regression',extras=current,previous_extras=last_good,previous_rate=best,windows=windows)
                tune(last_good,'Measured throughput regression: restore preceding accepted production capacity');current=last_good;break
            last_good=current;best=rate
            experiment.record('production_capacity_accepted',extras=current,photos_per_minute=rate,windows=windows)
    except KeyboardInterrupt as error:
        experiment.record('production_capacity_measurement_interrupted',reason=str(error),retained_extras=current);return
    except RuntimeError as error:
        experiment.record('production_capacity_negative_result',reason=str(error),extras=current,restore_extras=last_good)
        tune(last_good,'Measured instability/critical pressure: restore preceding accepted production capacity');current=last_good
    except Exception as error:
        # A diagnostic failure alone is not evidence to lower production capacity.
        experiment.record('production_capacity_observation_failed',error_type=type(error).__name__,retained_extras=current);raise
    final=request('/api/burst')['workers']['mac']
    experiment.record('production_capacity_finished',policy=final,photos_per_minute=best)
    (experiment.ROOT/'docs/reference/waffles-production-capacity.json').write_text(json.dumps({'policy':final,'observed_photos_per_minute':best,'quality_scope':'CPU configuration unchanged; labeled repeated validation completed at eight extras'},indent=2)+'\n')
    print(json.dumps(final))

if __name__=='__main__':main()
