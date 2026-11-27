#!/usr/bin/env python3
"""Prepare an honest PostgreSQL review run; never invent classifier probabilities.

One target per Sol call, a passing evaluation and independent visual acceptance
are required. The existing single API writer remains responsible for face/tag
writes, idempotency and bounded retries. Every original classifier row survives.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
from distributed import KUBE

spec=importlib.util.spec_from_file_location('report',Path(__file__).with_name('report-reject-review.py'))
report=importlib.util.module_from_spec(spec);spec.loader.exec_module(report)


def choose_box(boxes:list)->list|None:
    """Only auto-select one animal or near-duplicate overlapping detections."""
    if not boxes:return None
    for box in boxes:
        if len(box)!=4 or not all(isinstance(v,(int,float)) and math.isfinite(v) and 0<=v<=1 for v in box):raise ValueError('Invalid animal box')
        if box[0]>=box[2] or box[1]>=box[3]:raise ValueError('Empty animal box')
    def area(b):return (b[2]-b[0])*(b[3]-b[1])
    best=max(boxes,key=area)
    for b in boxes:
        intersection=max(0,min(best[2],b[2])-max(best[0],b[0]))*max(0,min(best[3],b[3])-max(best[1],b[1]))
        if intersection/(area(best)+area(b)-intersection)<.75:return None
    return best


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);p.add_argument('--apply',action='store_true');a=p.parse_args();os.umask(0o077)
    gate=json.loads((a.directory/'evaluation-gate-v3-single.json').read_text());assert gate['protocol_version']==3 and 'sol' in gate['eligible_models']
    manifest=json.loads((a.directory/'rejects.json').read_text());expected={r['asset_id']:r for r in manifest}
    batches,records=report.read_records(a.directory/'review-sol-v3-single')
    assert len(batches)==len(expected),'Review must settle the entire frozen cohort first'
    by_id={r['asset_id']:r for r in records};assert len(by_id)==len(records),'Duplicate decisions'
    assert set(by_id)<=set(expected)
    failed={asset for b in batches if b['status']!='complete' for asset in json.loads((a.directory/'review-sol-v3-single'/f"batch-{b['batch']:04}"/'submitted.json').read_text())['assets']}
    assert set(by_id)|failed==set(expected) and not set(by_id)&failed
    decisions=json.loads((a.directory/'visual-decisions.json').read_text());detections=json.loads((a.directory/'detections.json').read_text())
    manual_file=a.directory/'manual-boxes.json';manual=json.loads(manual_file.read_text()) if manual_file.exists() else {}
    if manual:
        checked=json.loads((a.directory/'manual-crop-check/verified.json').read_text())
        assert checked['manual_boxes_sha256']==hashlib.sha256(manual_file.read_bytes()).hexdigest()
        assert set(checked['indices'])==set(map(int,manual))
    candidates={str(r['review_index']) for r in records if r['answer']['verdict']=='same_dog' and r['answer']['confidence']=='high'}
    assert candidates<=set(decisions),'Every high-confidence nomination needs independent visual review'
    protocol=a.directory/'review-sol-v3-single/protocol.json';protocol_sha=hashlib.sha256(protocol.read_bytes()).hexdigest()
    inventory={r['id']:r for r in json.loads((a.directory.parent/'distributed/inventory.json').read_text())}
    elapsed={r['asset_id']:b['seconds'] for b in batches for r in b.get('records',[])}
    jobs=[];accepted=0;missing_box=0
    for source in manifest:
        asset=source['asset_id'];index=str(source['review_index']);r=by_id.get(asset);visual=decisions.get(index);image_sha=hashlib.sha256((a.directory/'targets'/(asset+'.jpg')).read_bytes()).hexdigest()
        match=[];size=None;box=None
        if visual and visual['decision']=='accept':
            assert index in candidates and visual['asset_id']==asset and visual['image_sha256']==image_sha
            detection=detections[index];assert detection['sha256']==image_sha
            size=detection['size'];box=choose_box(detection['boxes'])
            if index in manual:
                assert manual[index]['sha256']==image_sha
                box=choose_box([manual[index]['box']])
            if box is None:missing_box+=1
            else:
                match=[{'name':'Waffles','box':box,'probability':None,'review_confidence':'high','source':'sol_plus_independent_visual_review'}];accepted+=1
        review={'model':'gpt-6.2-sol','protocol_sha256':protocol_sha,'image_sha256':image_sha,'answer':r['answer'] if r else None,'visual':visual,'manual_box':manual.get(index),'box_pending':bool(visual and visual['decision']=='accept' and box is None)}
        result={'matches':match,'size':size,'unknown':int(not match),'low_confidence':0,'out_of_range':0,'review':review}
        jobs.append({'id':asset,'date':inventory[asset]['date'],'ordinal':int(index),'status':'failed' if asset in failed else 'classified' if match else 'complete','result':result,'seconds':elapsed.get(asset),'last_error':'frontier_review_failed' if asset in failed else None})
    config=json.loads((a.directory/'historical-classifier.json').read_text());config['review_protocol']={'model':'gpt-6.2-sol','version':3,'sha256':protocol_sha,'gate':gate,'automatic_classifier_threshold_unchanged':True}
    payload={'run':'waffles-reviewed-recovery-20261127','config':config,'jobs':jobs}
    encoded=json.dumps(payload,sort_keys=True,indent=2)+'\n';plan=a.directory/'recovery-plan.json'
    if plan.exists():assert plan.read_text()==encoded,'Immutable recovery plan changed'
    else:plan.write_text(encoded)
    summary={'run':payload['run'],'reviewed':len(records),'model_errors':len(failed),'qualified_nominations':len(candidates),'visually_accepted':sum(v['decision']=='accept' for v in decisions.values()),'ready_for_assignment':accepted,'accepted_box_pending':missing_box,'plan_sha256':hashlib.sha256(encoded.encode()).hexdigest(),'apply':a.apply}
    print(json.dumps(summary),flush=True)
    if not a.apply:return
    # Both backups must have completed validation, not merely exist mid-stream.
    backups=list((a.directory/'backup').glob('immich-*.dump.contents'));assert backups,'Verified Immich backup is required'
    assert list((a.directory/'backup').glob('waffles-*.dump')),'Queue backup is required'
    code="""import fs from 'node:fs';import {createRequire} from 'node:module';
const p=JSON.parse(fs.readFileSync(0,'utf8'));const {Client}=createRequire('/usr/src/app/server/package.json')('pg');
const db=new Client();await db.connect();await db.query('BEGIN');
try{
const old=(await db.query('SELECT config FROM waffles.runs WHERE id=$1 FOR UPDATE',[p.run])).rows[0];
if(old){
if(old.config.review_protocol.sha256!==p.config.review_protocol.sha256)throw Error('Existing review protocol differs');
const count=(await db.query('SELECT count(*)::int n FROM waffles.jobs WHERE run_id=$1',[p.run])).rows[0].n;
if(count!==p.jobs.length)throw Error('Existing review cohort differs');
console.log(JSON.stringify({existing:true,jobs:count}));
}else{
await db.query("INSERT INTO waffles.runs(id,mode,state,workers,config,started_at) VALUES($1,'production','paused','{}',$2,now())",[p.run,p.config]);
for(const j of p.jobs){await db.query(`INSERT INTO waffles.jobs(run_id,asset_id,taken_at,ordinal,status,worker,device,pool,result,processing_seconds,completed_at,last_error)
VALUES($1,$2,$3,$4,$5,'sol-review','enterprise','review',$6,$7,CASE WHEN $5='complete' THEN now() ELSE NULL END,$8)`,[p.run,j.id,j.date,j.ordinal,j.status,j.result,j.seconds,j.last_error]);}
await db.query("UPDATE waffles.runs SET state='running' WHERE id=$1",[p.run]);
console.log(JSON.stringify({created:true,jobs:p.jobs.length}));
}
await db.query('COMMIT');}catch(e){await db.query('ROLLBACK');throw e;}finally{await db.end();}"""
    process=subprocess.run(KUBE+['-n','immich-pilot','exec','-i','deployment/waffles-queue','--','node','--input-type=module','-e',code],input=json.dumps(payload),text=True,capture_output=True,timeout=180)
    if process.returncode:
        (a.directory/'recovery-submit.stderr').write_text(process.stderr);raise RuntimeError('Recovery submission failed; private diagnostics retained')
    print(process.stdout.strip());(a.directory/'recovery-submitted.json').write_text(json.dumps({**summary,'at':datetime.now(timezone.utc).isoformat()})+'\n')


if __name__=='__main__':main()
