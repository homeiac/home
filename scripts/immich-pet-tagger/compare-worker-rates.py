#!/usr/bin/env python3
"""Compare real committed rates per active process, accounting for changing counts."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import json
import subprocess
import urllib.parse
from distributed import KUBE

code='''import {createRequire} from 'node:module';const {Client}=createRequire('/usr/src/app/server/package.json')('pg');const db=new Client();await db.connect();await db.query('BEGIN READ ONLY');
const rows=(await db.query(`SELECT worker,pool,device,count(*)::int completed,avg(processing_seconds) processing_seconds FROM waffles.jobs WHERE run_id='historical-waffles' AND status='complete' AND completed_at>now()-interval '60 seconds' GROUP BY worker,pool,device ORDER BY worker,pool`)).rows;
console.log(JSON.stringify(rows));await db.query('ROLLBACK');await db.end();'''
rows=json.loads(subprocess.run(KUBE+['-n','immich-pilot','exec','-i','deployment/waffles-queue','--','node','--input-type=module','-'],input=code,text=True,capture_output=True,check=True).stdout)
selector='{worker=~"mac|still-fawn"}'
queries={name:f'{fn}((max by(worker,pool)(waffles_pool_active_instances{selector}))[1m:15s])' for name,fn in [('average','avg_over_time'),('minimum','min_over_time'),('maximum','max_over_time')]}
queries['k8s_cpu_cores']='sum by(pod)(rate(container_cpu_usage_seconds_total{namespace="immich-pilot",container="worker",pod=~"waffles-(worker|burst)-still-fawn-.*"}[1m]))'
queries['k8s_throttled_fraction']='sum by(pod)(rate(container_cpu_cfs_throttled_periods_total{namespace="immich-pilot",container="worker",pod=~"waffles-(worker|burst)-still-fawn-.*"}[1m])) / sum by(pod)(rate(container_cpu_cfs_periods_total{namespace="immich-pilot",container="worker",pod=~"waffles-(worker|burst)-still-fawn-.*"}[1m]))'
def query(item):
 name,expr=item
 path='/api/v1/namespaces/monitoring/services/http:kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?'+urllib.parse.urlencode({'query':expr})
 data=json.loads(subprocess.check_output(KUBE+['get','--raw',path],text=True))['data']['result']
 return name,[{'labels':r['metric'],'value':float(r['value'][1])} for r in data]
with ThreadPoolExecutor(max_workers=5) as pool:metrics=dict(pool.map(query,queries.items()))
for r in rows:
 if r['worker'] not in ['mac','still-fawn']:continue
 for kind in ['average','minimum','maximum']:
  r[kind+'_active_processes']=next((m['value'] for m in metrics[kind] if m['labels']['worker']==r['worker'] and m['labels']['pool']==r['pool']),None)
 n=r['average_active_processes'];r['estimated_photos_per_minute_per_process']=r['completed']/n if n else None
print(json.dumps({'at':datetime.now(timezone.utc).isoformat(),'window_seconds':60,'rows':[r for r in rows if r['worker'] in ['mac','still-fawn']],
 'still_fawn_resources':{k:v for k,v in metrics.items() if k.startswith('k8s_')},
 'limits':'Different production photos, not matched hardware benchmark. Per-process denominator uses 15-second telemetry; changing counts make it approximate. Processing includes fetch and inference, excludes claim and finish.'},indent=2))
