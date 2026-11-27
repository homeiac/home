#!/usr/bin/env python3
"""Run a no-write fallback canary, then an auditable recovery of failed previews."""
import argparse
import base64
from collections import Counter
import json
from pathlib import Path
import subprocess
from distributed import KUBE, request

p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['canary','run','status','evaluate']);p.add_argument('directory',type=Path);args=p.parse_args()
canary='waffles-media-canary-20261127';production='waffles-media-recovery-20261127'
assets=json.loads((args.directory/'assets.json').read_text())
inventory={r['id']:r for r in json.loads((args.directory.parent/'distributed/inventory.json').read_text())}
truth=json.loads((args.directory.parent/'owner-confirmed-holdout.json').read_text())
if args.mode in ['canary','run']:
    identifier=canary if args.mode=='canary' else production
    selected=assets
    if args.mode=='canary':
        ids=list(dict.fromkeys([r['id'] for r in assets[:8]]+truth['positive']+truth['negative']))
        selected=[inventory[i] for i in ids]
    else:
        gate=json.loads((args.directory/'canary-result.json').read_text())
        assert gate['passed'], 'Canary must pass before production recovery'
    existing=[r for r in request('/admin/status')['runs'] if r['id']==identifier]
    if not existing:
        request('/admin/run',{'id':identifier,'mode':'benchmark' if args.mode=='canary' else 'production',
            'workers':['mac','still-fawn','pve','fun-bedbug'],
            'assets':[{'id':r['id'],'date':r['date']} for r in selected]})
    request('/admin/state',{'id':identifier,'state':'running'})
    print(json.dumps({'run':identifier,'assets':len(selected),'mode':args.mode}))
elif args.mode=='status':
    data=request('/admin/status')
    for identifier in [canary,production]:
        rs=[r for r in data['runs'] if r['id']==identifier]
        print(json.dumps({'run':identifier,'states':sorted(set(r['state'] for r in rs)),
          'counts':dict(Counter({s:sum(r['jobs'] for r in rs if r['status']==s) for s in set(r['status'] for r in rs)})),
          'completed_by_backend':{r['worker']:r['jobs'] for r in rs if r['status']=='complete'},
          'assignments_added':sum(r.get('assignments') or 0 for r in rs)}))
else:
    code='''import {createRequire} from 'node:module';const {Client}=createRequire('/usr/src/app/server/package.json')('pg');const db=new Client();await db.connect();
const rows=(await db.query("SELECT asset_id,status,result,last_error FROM waffles.jobs WHERE run_id=$1",[process.argv[2]])).rows;
await db.end();console.log(JSON.stringify(rows));'''
    r=subprocess.run(KUBE+['-n','immich-pilot','exec','-i','deployment/waffles-queue','--','node','--input-type=module','-',canary],input=code,text=True,capture_output=True,check=True)
    rows=json.loads(r.stdout);by_id={r['asset_id']:r for r in rows}
    assert rows and all(r['status']=='complete' for r in rows),'Canary has incomplete/failed jobs'
    (args.directory/'canary-rows.json').write_text(json.dumps(rows,indent=2)+'\n')
    positive=sum(bool(by_id[i]['result']['matches']) for i in truth['positive'])
    false_positive=sum(bool(by_id[i]['result']['matches']) for i in truth['negative'])
    video_controls=[assets[i]['id'] for i in [1,2,3,4,7]]
    video_fp=sum(bool(by_id[i]['result']['matches']) for i in video_controls)
    video_positive=sum(bool(by_id[assets[i]['id']]['result']['matches']) for i in [0,5])
    report={'run':canary,'completed':len(rows),'holdout_true_positive':positive,'holdout_false_positive':false_positive,
       'video_control_false_positive':video_fp,'clear_waffles_video_matches':video_positive,
       'passed':positive>=9 and false_positive==0 and video_fp==0}
    (args.directory/'canary-result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
