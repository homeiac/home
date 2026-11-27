#!/usr/bin/env python3
"""Print compact journal progress without exposing private photo identifiers."""
import json
from pathlib import Path
from distributed import request

path=Path(__file__).resolve().parents[2]/'docs/experiments/waffles/2026-11-26-continuous-production.jsonl'
rows=[json.loads(line) for line in path.read_text().splitlines()]
start=max(i for i,r in enumerate(rows) if r['event']=='protocol')
recent=rows[start:]
for row in recent:
    if row['event'] in ('trial_finished','trial_failed','trial_skipped','backend_selected','experiment_failed','experiment_completed'):
        print(json.dumps({k:v for k,v in row.items() if k in ('at','event','run','worker','slots','device','cores','photos_per_minute','accuracy','valid','reason')}))
print('Latest event:',recent[-1]['event'],recent[-1]['at'])
policy=next((r for r in reversed(recent) if r['event']=='extra_policy_requested'),{})
print('Latest requested extras:',{k:policy[k] for k in ('worker','slots','device','cpu_cores') if k in policy})
status=request('/admin/status')
print('Workers:',json.dumps([{k:w[k] for k in ('name','base_instances','burst_instances','burst_devices','burst_cpu_affinity','unexpected_exits')} for w in status['workers']]))
session=recent[0]['session'];runs={}
for row in status['runs']:
    if (row['id'].startswith('burst-'+session) and row['state']=='running') or row['id']=='historical-waffles':
        counts=runs.setdefault(row['id'],{});counts[row['status']]=counts.get(row['status'],0)+row['jobs']
print('Progress:',json.dumps(runs))
