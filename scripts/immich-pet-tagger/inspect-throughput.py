#!/usr/bin/env python3
"""Compare rolling throughput with and without duplicate exporter pod series."""
from datetime import datetime,timezone
import json
import subprocess
import urllib.parse
from distributed import KUBE

metric='waffles_jobs{run="historical-waffles",state="complete"}'
queries={
 'old_by_pod':f'60*sum by(worker,pod)(clamp_min(deriv({metric}[5m]),0))',
 'corrected_by_worker':f'60*sum by(worker)(clamp_min(deriv((max by(run,worker,state)({metric}))[5m:15s]),0))',
 'durable_totals':f'max by(worker)({metric})'}
for stamp in ['2026-11-27T05:42:30Z','2026-11-27T05:43:30Z','2026-11-27T05:44:30Z','2026-11-27T05:45:30Z']:
    output={'at':stamp}
    for name,query in queries.items():
        path='/api/v1/namespaces/monitoring/services/http:kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?'+urllib.parse.urlencode({'query':query,'time':stamp})
        data=json.loads(subprocess.check_output(KUBE+['get','--raw',path],text=True))
        assert data['status']=='success'
        output[name]=[{'worker':r['metric'].get('worker'),'pod':r['metric'].get('pod'),'value':round(float(r['value'][1]),3)} for r in data['data']['result']]
    print(json.dumps(output))
