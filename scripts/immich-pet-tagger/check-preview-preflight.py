#!/usr/bin/env python3
"""Report background preview scan progress without exposing photo identifiers."""
import json
import subprocess
from distributed import KUBE

subprocess.run(KUBE+['-n','immich-pilot','get','job','waffles-preview-preflight-v1'],check=True)
subprocess.run(KUBE+['-n','immich-pilot','logs','job/waffles-preview-preflight-v1','--tail=5'],check=True)
code='''import {createRequire} from 'node:module';
const {Client}=createRequire('/usr/src/app/server/package.json')('pg');
const db=new Client();await db.connect();await db.query('BEGIN READ ONLY');
await db.query("SET LOCAL statement_timeout='10s'");
const report={};
report.audit=(await db.query(`SELECT p.state,count(*)::int assets,sum(p.attempts)::int http_attempts,
 count(*) FILTER(WHERE p.removed)::int removed,
 count(*) FILTER(WHERE j.status='pending')::int still_pending_inference
 FROM waffles.preview_checks p JOIN waffles.jobs j USING(run_id,asset_id)
 WHERE p.run_id='historical-waffles' GROUP BY p.state`)).rows;
report.integrity=(await db.query(`SELECT count(*)::int removed_records,
 count(*) FILTER(WHERE p.not_found<>4 OR p.attempts<>4 OR p.last_status<>404)::int invalid_evidence,
 count(*) FILTER(WHERE j.status<>'failed' OR j.last_error<>'thumbnail_http_404')::int unexpected_job_state
 FROM waffles.preview_checks p JOIN waffles.jobs j USING(run_id,asset_id) WHERE p.removed`)).rows;
report.production=(await db.query(`SELECT worker,count(*)::int completed_last_minute
 FROM waffles.jobs WHERE run_id='historical-waffles' AND status='complete'
 AND completed_at>now()-interval '1 minute' GROUP BY worker`)).rows;
await db.query('ROLLBACK');await db.end();console.log(JSON.stringify(report));'''
result=subprocess.run(KUBE+['-n','immich-pilot','exec','-i','deployment/waffles-queue','--','node','--input-type=module','-'],input=code,text=True,capture_output=True,check=True,timeout=30)
print(json.dumps(json.loads(result.stdout),indent=2))
