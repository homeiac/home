#!/usr/bin/env python3
"""Read-only aggregate queue timings and PostgreSQL activity; no photo IDs."""
import json
import subprocess
from distributed import KUBE

code='''import {createRequire} from 'node:module';
const {Client}=createRequire('/usr/src/app/server/package.json')('pg');const db=new Client();await db.connect();
await db.query('BEGIN READ ONLY');await db.query("SET LOCAL statement_timeout='10s'");
const queries={
recent:`SELECT worker,pool,device,count(*)::int completed,round(avg(processing_seconds)::numeric,4) processing_mean,
 percentile_cont(.5) WITHIN GROUP(ORDER BY processing_seconds) processing_p50,
 percentile_cont(.95) WITHIN GROUP(ORDER BY processing_seconds) processing_p95
 FROM waffles.jobs WHERE completed_at>now()-interval '3 minutes' AND run_id='historical-waffles' AND status='complete'
 GROUP BY worker,pool,device ORDER BY worker,pool`,
base_cycles:`WITH samples AS (SELECT worker,completed_at,processing_seconds,
 extract(epoch FROM completed_at-lag(completed_at) OVER(PARTITION BY worker ORDER BY completed_at)) cycle
 FROM waffles.jobs WHERE completed_at>now()-interval '3 minutes' AND run_id='historical-waffles' AND status='complete' AND pool='base')
 SELECT worker,count(cycle)::int intervals,avg(cycle) completion_cycle_mean,avg(processing_seconds) processing_mean FROM samples WHERE cycle IS NOT NULL GROUP BY worker`,
activity:`SELECT application_name,state,wait_event_type,wait_event,count(*)::int connections,max(extract(epoch FROM now()-query_start)) age_seconds
 FROM pg_stat_activity WHERE datname=current_database() GROUP BY application_name,state,wait_event_type,wait_event`,
tables:`SELECT relname,n_live_tup,n_dead_tup,seq_scan,idx_scan FROM pg_stat_user_tables WHERE schemaname='waffles' AND relname IN ('jobs','runs','settings')`,
extensions:`SELECT extname FROM pg_extension WHERE extname='pg_stat_statements'`};
const report={};for(const [name,sql] of Object.entries(queries))report[name]=(await db.query(sql)).rows;
await db.query('COMMIT');await db.end();console.log(JSON.stringify(report));'''
result=subprocess.run(KUBE+['-n','immich-pilot','exec','-i','deployment/waffles-queue','--','node','--input-type=module','-'],input=code,text=True,capture_output=True,check=True)
print(json.dumps(json.loads(result.stdout),indent=2))
