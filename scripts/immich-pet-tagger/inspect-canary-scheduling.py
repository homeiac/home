#!/usr/bin/env python3
"""Explain run eligibility, including empty runs hidden by the status inner join."""
import subprocess
from distributed import KUBE
code = '''import {createRequire} from 'node:module';
const {Client}=createRequire('/usr/src/app/server/package.json')('pg');
const db=new Client();await db.connect();
console.log(JSON.stringify((await db.query(`SELECT r.id,r.mode,r.state,r.workers,
count(j.asset_id)::int jobs,count(j.asset_id) FILTER(WHERE j.status='pending')::int pending
FROM waffles.runs r LEFT JOIN waffles.jobs j ON j.run_id=r.id
WHERE r.state='running' GROUP BY r.id ORDER BY r.created_at`)).rows));
await db.end();'''
subprocess.run(KUBE+['-n','immich-pilot','exec','-i','deployment/waffles-queue','--','node','--input-type=module','-'],input=code,text=True,check=True)
