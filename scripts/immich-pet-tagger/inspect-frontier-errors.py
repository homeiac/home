#!/usr/bin/env python3
"""Inspect only structured model transport/schema failures, never prompt images or credentials."""
import argparse
import json
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);a=p.parse_args()
for file in sorted(a.directory.glob('eval-*/batch-*/settled.json')):
    result=json.loads(file.read_text())
    if result['status']=='complete':continue
    row={'model':file.parent.parent.name,'batch':result['batch'],'error':result.get('error')}
    answer=file.parent/'answer.json'
    if answer.exists():
        try:
            data=json.loads(answer.read_text());row['answer_keys']=list(data)
            row['target_indices']=[v.get('target_index') for v in data.get('results',[])];row['verdicts']=[v.get('verdict') for v in data.get('results',[])]
        except ValueError:row['answer_json_valid']=False
    events=file.parent/'events.jsonl'
    if events.exists():
        for line in events.read_text().splitlines():
            try:e=json.loads(line)
            except ValueError:continue
            if e.get('type') in ('error','turn.failed'):row.setdefault('runtime_errors',[]).append(str(e)[:700])
    print(json.dumps(row))
