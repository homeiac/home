#!/usr/bin/env python3
"""Read benchmark outcomes privately; publish aggregate timing and agreement only."""
import argparse
from datetime import datetime
import hashlib
import json
import logging
from pathlib import Path
import subprocess
from distributed import KUBE


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--holdout', type=Path)
    args = parser.parse_args()
    code = '''import {createRequire} from 'node:module';
const {Client}=createRequire('/usr/src/app/server/package.json')('pg');
const db=new Client(); await db.connect();
const rows=(await db.query(`SELECT r.id,r.state,r.started_at,j.asset_id,j.worker,j.status,j.processing_seconds,j.completed_at,j.result
 FROM waffles.runs r JOIN waffles.jobs j ON j.run_id=r.id
 WHERE r.mode='benchmark' ORDER BY r.id,j.ordinal`)).rows;
console.log(JSON.stringify(rows)); await db.end();'''
    result = subprocess.run(KUBE+['-n','immich-pilot','exec','-i','deployment/waffles-queue','--','node','--input-type=module','-'], input=code, text=True, capture_output=True, check=True)
    rows = json.loads(result.stdout)
    report = {'method': '96 identical photos, warm models, ABBA ordering, reverse second pass; no Immich writes; wall time ends at last committed result', 'runs': []}
    for name in sorted({r['id'] for r in rows if not r['id'].startswith('warmup-')}):
        items = [r for r in rows if r['id']==name]
        complete = [r for r in items if r['status']=='complete']
        if len(complete)!=len(items):
            raise RuntimeError(f'{name} is not complete')
        seconds=(max(datetime.fromisoformat(r['completed_at']) for r in complete)-datetime.fromisoformat(items[0]['started_at'])).total_seconds()
        entry = dict(run=name, photos=len(items), wall_seconds=round(seconds,3), photos_per_minute=round(60*len(items)/seconds,2),
                     sample_sha256=hashlib.sha256('\n'.join(sorted(r['asset_id'] for r in items)).encode()).hexdigest(), backends={})
        for worker in sorted({r['worker'] for r in items}):
            subset=[r for r in items if r['worker']==worker]
            entry['backends'][worker]=dict(photos=len(subset), mean_processing_seconds=round(sum(r['processing_seconds'] for r in subset)/len(subset),3))
        if name.startswith('holdout-') and args.holdout:
            truth=json.loads(args.holdout.read_text())
            entry['accuracy']={label:dict(total=len(truth[label]), matched=sum(bool(r['result']['matches']) for r in items if r['asset_id'] in truth[label])) for label in ['positive','negative']}
        report['runs'].append(entry)
    baseline={r['asset_id']:bool(r['result']['matches']) for r in rows if r['id']=='before-1' and r['status']=='complete'}
    report['agreement']={name:dict(compared=sum(r['asset_id'] in baseline for r in rows if r['id']==name), different=sum(bool(r['result']['matches'])!=baseline[r['asset_id']] for r in rows if r['id']==name and r['asset_id'] in baseline and r['status']=='complete')) for name in ['after-1','after-2','before-2']}
    if args.output:
        args.output.write_text(json.dumps(report,indent=2)+'\n')
    logging.basicConfig(level=logging.INFO,format='%(message)s')
    logging.info('%s',json.dumps(report,indent=2))


if __name__=='__main__':
    main()
