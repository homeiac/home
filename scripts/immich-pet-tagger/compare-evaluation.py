#!/usr/bin/env python3
"""Compare old private evaluations with the durable CPU holdout, without printing asset IDs."""
import argparse
import json
from pathlib import Path
import subprocess
from distributed import KUBE

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('directory',type=Path)
args=parser.parse_args()
code="""import {createRequire} from 'node:module'; const {Client}=createRequire('/usr/src/app/server/package.json')('pg');
const db=new Client();await db.connect();console.log(JSON.stringify((await db.query("SELECT asset_id,result FROM waffles.jobs WHERE run_id='holdout-still-fawn'")).rows));await db.end();"""
rows=json.loads(subprocess.check_output(KUBE+['-n','immich-pilot','exec','-i','deployment/waffles-queue','--','node','--input-type=module','-'],input=code,text=True))
new={r['asset_id']:bool(r['result']['matches']) for r in rows}
for path in sorted(args.directory.glob('evaluation*.log')):
    for line in path.read_text().splitlines():
        try: data=json.loads(line)
        except ValueError: continue
        if 'results' not in data: continue
        compared=[r for r in data['results'] if r['asset'] in new]
        differences=[dict(expected=r['expected'],old=r['matched'],new=new[r['asset']],old_predictions=r['predictions']) for r in compared if r['matched']!=new[r['asset']]]
        print(json.dumps(dict(file=path.name,old_counts=data['counts'],compared=len(compared),differences=differences)))
