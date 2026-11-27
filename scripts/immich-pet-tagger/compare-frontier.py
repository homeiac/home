#!/usr/bin/env python3
"""Measure incremental recovery on local misses, keeping photo identities private."""
import argparse
import json
from pathlib import Path
import subprocess
from distributed import KUBE

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('directory',type=Path)
parser.add_argument('--output',type=Path)
args=parser.parse_args()
code="""import {createRequire} from 'node:module'; const {Client}=createRequire('/usr/src/app/server/package.json')('pg');
const db=new Client();await db.connect();console.log(JSON.stringify((await db.query("SELECT asset_id,result FROM waffles.jobs WHERE run_id='holdout-still-fawn'")).rows));await db.end();"""
rows=json.loads(subprocess.check_output(KUBE+['-n','immich-pilot','exec','-i','deployment/waffles-queue','--','node','--input-type=module','-'],input=code,text=True))
local={r['asset_id']:bool(r['result']['matches']) for r in rows}
report=[]
for directory in sorted(args.directory.glob('frontier-*')):
    if not (directory/'summary.json').exists():continue
    summary=json.loads((directory/'summary.json').read_text())
    results=[json.loads(p.read_text()) for p in directory.glob('*/result.json')]
    recovered=[r for r in results if not local[r['asset']] and r['expected']=='positive' and r['answer']['verdict']=='same_dog' and r['answer']['confidence']=='high']
    summary['additional_local_misses_recovered']=len(recovered)
    summary['eligible_for_fallback']=summary['false_positive']==0 and len(recovered)>0
    report.append(summary)
if args.output:args.output.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
