#!/usr/bin/env python3
"""EXPLAIN only the SELECT portion of claiming, without locks or job mutations."""
import argparse
import json
import subprocess
from distributed import KUBE

parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--full-plan-only',action='store_true');args=parser.parse_args()
code='''import {createRequire} from 'node:module';
import {CLAIM_SQL} from '/code/queue-core.mjs';
const {Client}=createRequire('/usr/src/app/server/package.json')('pg');const db=new Client();await db.connect();
let select=CLAIM_SQL.slice('WITH candidate AS ('.length,CLAIM_SQL.indexOf(')\\n UPDATE waffles.jobs'));
select=select.replace(' FOR UPDATE OF j SKIP LOCKED','').replaceAll('$3','$2');
if(!select.trimStart().startsWith('SELECT')||/UPDATE|INSERT|DELETE|FOR UPDATE/.test(select))throw Error('Not a read-only candidate');
await db.query('BEGIN READ ONLY');await db.query("SET LOCAL statement_timeout='10s'");
const output={};
if(process.argv[2]==='plan-only') {
 output.full_plan=(await db.query('EXPLAIN (FORMAT JSON) '+CLAIM_SQL,['mac','00000000-0000-4000-8000-000000000000','base','mps'])).rows[0]['QUERY PLAN'];
} else for(const [worker,lane] of [['mac','base'],['mac','burst'],['still-fawn','base']])
 output[worker+'-'+lane]=(await db.query('EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) '+select,[worker,lane])).rows[0]['QUERY PLAN'];
await db.query('ROLLBACK');await db.end();console.log(JSON.stringify(output));'''
result=subprocess.run(KUBE+['-n','immich-pilot','exec','-i','deployment/waffles-queue','--','node','--input-type=module','-','plan-only' if args.full_plan_only else 'select-timing'],input=code,text=True,capture_output=True)
if result.returncode:
    print(result.stderr);raise SystemExit(result.returncode)
print(json.dumps(json.loads(result.stdout),indent=2))
