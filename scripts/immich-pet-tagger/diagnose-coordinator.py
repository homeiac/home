#!/usr/bin/env python3
"""Read coordinator CPU quota saturation and memory from Prometheus; no mutations."""
from concurrent.futures import ThreadPoolExecutor
import json
import subprocess
import urllib.parse
from distributed import KUBE

selector='{namespace="immich-pilot",container="queue",pod=~"waffles-queue-.*"}'
queries={
 'cpu_cores':'sum by(pod)(rate(container_cpu_usage_seconds_total'+selector+'[3m]))',
 'throttled_period_fraction':'sum by(pod)(rate(container_cpu_cfs_throttled_periods_total'+selector+'[3m])) / sum by(pod)(rate(container_cpu_cfs_periods_total'+selector+'[3m]))',
 'working_set_bytes':'max by(pod)(container_memory_working_set_bytes'+selector+')'}
def query(item):
    name,expr=item
    path='/api/v1/namespaces/monitoring/services/http:kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?'+urllib.parse.urlencode({'query':expr})
    result=json.loads(subprocess.check_output(KUBE+['get','--raw',path],text=True,timeout=20))
    return name,[{'pod':r['metric'].get('pod'),'value':float(r['value'][1])} for r in result['data']['result']]
with ThreadPoolExecutor(max_workers=3) as pool:print(json.dumps(dict(pool.map(query,queries.items())),indent=2))
