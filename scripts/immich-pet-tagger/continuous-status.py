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
    if row['event'] in ('trial_finished','backend_selected','experiment_failed','experiment_completed'):
        print(json.dumps({k:v for k,v in row.items() if k not in ('candidates','production_end')}))
print('Latest event:',recent[-1]['event'],recent[-1]['at'])
status=request('/admin/status')
print('Workers:',json.dumps(status['workers']))
session=recent[0]['session'];runs={}
for row in status['runs']:
    if (row['id'].startswith('burst-'+session) and row['state']=='running') or row['id']=='historical-waffles':
        counts=runs.setdefault(row['id'],{});counts[row['status']]=counts.get(row['status'],0)+row['jobs']
print('Progress:',json.dumps(runs))
