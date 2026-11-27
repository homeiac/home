#!/usr/bin/env python3
"""Verify bounded production writes, then start the already-approved historical queue."""
import argparse
import json
import logging
from pathlib import Path
import subprocess
import time
from distributed import KUBE, request


def main() -> None:
    logging.basicConfig(level=logging.INFO,format='%(message)s')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('holdout',type=Path)
    parser.add_argument('inventory',type=Path)
    parser.add_argument('report',type=Path)
    args=parser.parse_args()
    report=json.loads(args.report.read_text())
    checks=[r for r in report['runs'] if r['run'].startswith('holdout-')]
    assert len(checks)==3 and all(r['accuracy']['negative']['matched']==0 and r['accuracy']['positive']['matched']>=9 for r in checks)
    assert all(a['compared']==96 and a['different']==0 for a in report['agreement'].values())
    truth=json.loads(args.holdout.read_text());ids=set(truth['positive']+truth['negative'])
    assets=[a for a in json.loads(args.inventory.read_text()) if a['id'] in ids]
    assert len(assets)==26
    name='validation-write'
    if not any(r['id']==name for r in request('/admin/status')['runs']):
        request('/admin/run',dict(id=name,mode='production',workers=['mac','pve','still-fawn'],assets=assets))
        request('/admin/state',dict(id=name,state='running'))
    deadline=time.monotonic()+900
    while True:
        rows=[r for r in request('/admin/status')['runs'] if r['id']==name]
        done=sum(r['jobs'] for r in rows if r['status']=='complete')
        logging.info('Bounded production validation: %d/26 committed',done)
        if any(r['status']=='failed' for r in rows) or time.monotonic()>deadline:
            request('/admin/state',dict(id=name,state='paused'))
            raise RuntimeError('Production validation did not complete; historical run remains paused')
        if done==26:break
        time.sleep(15)
    # Verify actual Immich state, not merely queue counters. Credentials stay in
    # the existing coordinator environment and only aggregate counts leave it.
    code='''import {createRequire} from 'node:module';
const {Client}=createRequire('/usr/src/app/server/package.json')('pg');
const db=new Client();await db.connect();
const person=(await db.query("SELECT config FROM waffles.runs WHERE id='validation-write'")).rows[0].config.person_id;
await db.end();
const result={positive:0,negative:0,duplicate_faces:0};
for(const [label,ids] of Object.entries(TRUTH))for(const id of ids){
 const response=await fetch((process.env.IMMICH_URL??'http://immich-server.immich-pilot.svc.cluster.local:2283')+'/api/faces?id='+id,{headers:{'x-api-key':process.env.IMMICH_API_KEY}});
 if(!response.ok)throw Error('Face verification HTTP '+response.status);
 const count=(await response.json()).filter(f=>(f.person?.id??f.personId)===person).length;
 result[label]+=Number(count>0);result.duplicate_faces+=Number(count>1);
}
console.log(JSON.stringify(result));'''
    output=subprocess.run(KUBE+['-n','immich-pilot','exec','-i','deployment/waffles-queue','--','node','--input-type=module','-'],
                          input='const TRUTH='+json.dumps(truth)+';\n'+code,text=True,capture_output=True,check=True)
    verified=json.loads(output.stdout)
    assert verified['positive']>=9 and verified['negative']==0 and verified['duplicate_faces']==0, verified
    logging.info('Verified Immich face assignments: %s',verified)
    request('/admin/state',dict(id='historical-waffles',state='running'))
    request('/admin/discovery',dict(enabled=True,since='2026-11-26T00:00:00Z'))
    logging.info('Historical backfill running on Mac + PVE + still-fawn; hourly discovery enabled; RTX unused')


if __name__=='__main__':
    main()
