#!/usr/bin/env python3
"""Apply explicit owner identity confirmations using the existing single writer.

Input is a private manifest with run_id, confirmation, and assets containing
asset_id, image_sha256 and normalized box. Preserve prior model decisions and
snapshot prior face state before enqueuing. No model call or retraining occurs.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import logging
import os
from pathlib import Path
import subprocess
import time

from PIL import Image
from distributed import KUBE

spec = importlib.util.spec_from_file_location('review_recovery', Path(__file__).with_name('prepare-reviewed-recovery.py'))
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


def remote(code: str, payload: dict, directory: Path) -> dict:
    """Run bounded operations with credentials confined to the queue pod."""
    result = subprocess.run(KUBE + ['-n', 'immich-pilot', 'exec', '-i',
        'deployment/waffles-queue', '--', 'node', '--input-type=module', '-e', code],
        input=json.dumps(payload), text=True, capture_output=True, timeout=90)
    if result.returncode:
        (directory/'owner-confirmation-error.log').write_text(result.stderr)
        raise RuntimeError('Operation failed; private diagnostics retained')
    return json.loads(result.stdout)


COMMON = """import fs from 'node:fs';import {createRequire} from 'node:module';
const p=JSON.parse(fs.readFileSync(0,'utf8'));
const {Client}=createRequire('/usr/src/app/server/package.json')('pg');
const db=new Client();await db.connect();
const source=(await db.query('SELECT config FROM waffles.runs WHERE id=$1',[p.source_run])).rows[0];
if(!source)throw Error('Source review missing');
const base=process.env.IMMICH_URL??'http://immich-server.immich-pilot.svc.cluster.local:2283';
async function faces(id){const r=await fetch(base+'/api/faces?id='+id,{headers:{'x-api-key':process.env.IMMICH_API_KEY},signal:AbortSignal.timeout(15000)});if(!r.ok)throw Error('Face readback HTTP '+r.status);return await r.json();}
"""


def main() -> None:
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    payload = json.loads(args.manifest.read_text())
    assert payload['confirmation']['confirmed_by'] == 'owner'
    assert payload['confirmation']['statement'] and payload['confirmation']['at']
    assets = payload['assets']
    assert assets and len({r['asset_id'] for r in assets}) == len(assets)
    inventory = {r['id']: r for r in json.loads((args.directory.parent/'distributed/inventory.json').read_text())}
    for row in assets:
        path = args.directory/'targets'/(row['asset_id']+'.jpg')
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row['image_sha256']
        assert recovery.choose_box([row['box']]) == row['box']
        with Image.open(path) as image:
            row['size'] = list(image.size)
        row['date'] = inventory[row['asset_id']]['date']
    payload['manifest_sha256'] = hashlib.sha256(args.manifest.read_bytes()).hexdigest()
    logging.info('Validated %d owner-confirmed targets; apply=%s', len(assets), args.apply)
    if not args.apply:
        return
    assert list((args.directory/'backup').glob('immich-*.dump.contents')), 'Verified full backup required'
    snapshot = args.directory/(payload['run_id']+'-before.json')
    if not snapshot.exists():
        before = remote(COMMON + """
const rows=[];for(const a of p.assets){
const prior=(await db.query('SELECT * FROM waffles.jobs WHERE run_id=$1 AND asset_id=$2',[p.source_run,a.asset_id])).rows[0];
if(!prior||prior.status!=='complete'||prior.result.matches.length)throw Error('Expected unassigned settled review');
rows.push({prior,faces:await faces(a.asset_id)});}
await db.end();console.log(JSON.stringify({rows}));""", payload, args.directory)
        snapshot.write_text(json.dumps(before, indent=2)+'\n')
    logging.info('Saved prior decisions and face state; submitting idempotent owner-confirmation run')
    remote(COMMON + """
await db.query('BEGIN');try{
const old=(await db.query('SELECT config FROM waffles.runs WHERE id=$1 FOR UPDATE',[p.run_id])).rows[0];
if(old){if(old.config.owner_confirmation?.manifest_sha256!==p.manifest_sha256)throw Error('Existing manifest differs');}
else{
const config={...source.config,owner_confirmation:{...p.confirmation,manifest_sha256:p.manifest_sha256}};
await db.query("INSERT INTO waffles.runs(id,mode,state,workers,config,started_at) VALUES($1,'production','paused','{}',$2,now())",[p.run_id,config]);
for(const [i,a] of p.assets.entries()){
const result={size:a.size,matches:[{name:'Waffles',box:a.box,probability:null,source:'owner_confirmed'}],unknown:0,low_confidence:0,out_of_range:0,owner_confirmation:{...p.confirmation,image_sha256:a.image_sha256,box_source:'assistant visual placement'}};
await db.query("INSERT INTO waffles.jobs(run_id,asset_id,taken_at,ordinal,status,worker,device,pool,result) VALUES($1,$2,$3,$4,'classified','owner-review','human','review',$5)",[p.run_id,a.asset_id,a.date,i,result]);}
await db.query("UPDATE waffles.runs SET state='running' WHERE id=$1",[p.run_id]);}
await db.query('COMMIT');}catch(e){await db.query('ROLLBACK');throw e;}finally{await db.end();}
console.log(JSON.stringify({submitted:true}));""", payload, args.directory)
    deadline = time.monotonic()+120
    while True:
        result = remote(COMMON + """
const jobs=(await db.query('SELECT asset_id,status,applied,last_error FROM waffles.jobs WHERE run_id=$1',[p.run_id])).rows;
const run=(await db.query('SELECT state FROM waffles.runs WHERE id=$1',[p.run_id])).rows[0];
for(const j of jobs)j.waffles_faces=(await faces(j.asset_id)).filter(f=>(f.person?.id??f.personId)===source.config.person_id).length;
await db.end();console.log(JSON.stringify({state:run.state,jobs}));""", payload, args.directory)
        (args.directory/(payload['run_id']+'-readback.json')).write_text(json.dumps(result, indent=2)+'\n')
        logging.info('Readback: %d/%d completed', sum(r['status']=='complete' for r in result['jobs']), len(assets))
        if any(r['status']=='failed' for r in result['jobs']):
            raise RuntimeError('Coordinator exhausted retries; inspect private readback')
        if result['state']=='complete' and len(result['jobs'])==len(assets) and all(r['status']=='complete' and r['waffles_faces']==1 for r in result['jobs']):
            break
        if time.monotonic()>deadline:
            raise RuntimeError('Verification deadline; existing run remains resumable')
        time.sleep(3)
    report = {'at':datetime.now(timezone.utc).isoformat(), 'run':payload['run_id'],
        'state':result['state'], 'owner_confirmed':len(assets),
        'verified_unique_assignments':len(result['jobs']), 'duplicate_faces':0,
        'new_faces_added':sum(r['applied'] for r in result['jobs']),
        'media':dict(Counter(inventory[r['asset_id']]['type'] for r in assets)),
        'source':'Explicit owner confirmation; not model evaluation or training data'}
    if args.output:
        args.output.write_text(json.dumps(report, indent=2)+'\n')
    logging.info('%s', json.dumps(report))


if __name__ == '__main__':
    main()
