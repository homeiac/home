#!/usr/bin/env python3
"""Correlate completed photos, preview failures and live capacity without mutations."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time
import urllib.parse
from distributed import KUBE

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--output', type=Path)
args = p.parse_args()
print('START: reading 20 minutes of production throughput and failure telemetry', flush=True)
code = '''import {createRequire} from 'node:module';
const {Client}=createRequire('/usr/src/app/server/package.json')('pg');
const db=new Client();await db.connect();await db.query('BEGIN READ ONLY');
await db.query("SET LOCAL statement_timeout='10s'");
const queries={
minutes:`SELECT date_trunc('minute',completed_at) AS bucket,worker,count(*)::int completed,
 round(avg(processing_seconds)::numeric,3) processing_seconds
 FROM waffles.jobs WHERE run_id='historical-waffles' AND status='complete'
 AND completed_at>now()-interval '20 minutes' GROUP BY 1,2 ORDER BY 1,2`,
queue:`SELECT status,last_error,count(*)::int jobs,min(ordinal) first_ordinal,max(ordinal) last_ordinal
 FROM waffles.jobs WHERE run_id='historical-waffles' GROUP BY 1,2`,
capacity:`SELECT worker,pool,device,count(*)::int ready_instances FROM waffles.instances
 WHERE ready AND NOT draining AND reported_at>now()-interval '30 seconds' GROUP BY 1,2,3`,
waits:`SELECT state,wait_event_type,wait_event,count(*)::int connections,
 max(extract(epoch FROM now()-query_start)) seconds FROM pg_stat_activity
 WHERE datname=current_database() AND state<>'idle' GROUP BY 1,2,3`
};const report={};for(const [name,sql] of Object.entries(queries))report[name]=(await db.query(sql)).rows;
await db.query('ROLLBACK');await db.end();console.log(JSON.stringify(report));'''
result = subprocess.run(KUBE + ['-n','immich-pilot','exec','-i','deployment/waffles-queue','--','node','--input-type=module','-'], input=code,text=True,capture_output=True,check=True,timeout=45)
report = {'at':datetime.now(timezone.utc).isoformat(),'database':json.loads(result.stdout)}
now = time.time()
queries = {
    'failed_previews': 'sum(max by(run,reason)(waffles_failed_jobs{run="historical-waffles",reason="thumbnail_http_404"}))',
    'active_instances': 'max by(worker,pool)(waffles_pool_active_instances)',
    'coordinator_cpu': 'sum(rate(container_cpu_usage_seconds_total{namespace="immich-pilot",pod=~"waffles-queue-.*",container!="",container!="POD"}[1m]))',
    'coordinator_throttled_fraction': 'sum(rate(container_cpu_cfs_throttled_periods_total{namespace="immich-pilot",pod=~"waffles-queue-.*",container!="",container!="POD"}[1m])) / sum(rate(container_cpu_cfs_periods_total{namespace="immich-pilot",pod=~"waffles-queue-.*",container!="",container!="POD"}[1m]))',
}
def query(item):
    name, expr = item
    path = '/api/v1/namespaces/monitoring/services/http:kube-prometheus-stack-prometheus:9090/proxy/api/v1/query_range?' + urllib.parse.urlencode({'query':expr,'start':now-1200,'end':now,'step':60})
    data = json.loads(subprocess.check_output(KUBE+['get','--raw',path],text=True,timeout=30))
    return name, data['data']['result']
with ThreadPoolExecutor(max_workers=4) as pool:
    report['telemetry'] = dict(pool.map(query,queries.items()))
report['limits'] = ['First and last database minute buckets are partial.', 'Failed-preview telemetry counts exhausted jobs, not individual attempts.', 'Completion timestamps measure committed results, not all attempted work.']
output = json.dumps(report,indent=2)+'\n'
if args.output:
    args.output.write_text(output)
    print('DONE: saved aggregate evidence to',args.output,flush=True)
else:
    print(output)
