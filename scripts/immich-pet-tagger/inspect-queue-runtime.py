#!/usr/bin/env python3
"""Read active job ages and PostgreSQL wait states without private asset identifiers."""
import subprocess
from distributed import KUBE
code='''import {createRequire} from 'node:module';const {Client}=createRequire('/usr/src/app/server/package.json')('pg');const db=new Client();await db.connect();
for(const [name,sql] of Object.entries({
jobs:`SELECT worker,pool,device,status,attempts,last_error,round(extract(epoch FROM lease_until-now()))::int lease_remaining FROM waffles.jobs WHERE status='running' ORDER BY worker`,
waits:`SELECT state,wait_event_type,wait_event,round(extract(epoch FROM now()-query_start))::int seconds,CASE WHEN query LIKE '%pg_advisory%' THEN 'advisory' WHEN query LIKE '%waffles%' THEN 'waffles' ELSE 'other' END query_kind FROM pg_stat_activity WHERE datname=current_database() AND state<>'idle'`,
retries:`SELECT status,last_error,count(*)::int jobs FROM waffles.jobs WHERE run_id='historical-waffles' AND attempts>1 GROUP BY status,last_error`
})){console.log(name,JSON.stringify((await db.query(sql)).rows));}await db.end();'''
subprocess.run(KUBE+['-n','immich-pilot','exec','-i','deployment/waffles-queue','--','node','--input-type=module','-'],input=code,text=True,check=True)
