#!/usr/bin/env python3
"""Read-only live validation of Immich dashboard queries through an existing pod."""
import json
import os
from pathlib import Path
import subprocess
import sys
import yaml

ROOT = Path(__file__).resolve().parents[2]
base = ['kubectl', '--kubeconfig', os.environ.get('KUBECONFIG', str(Path.home() / 'kubeconfig'))]
app = ROOT / 'gitops/clusters/homelab/apps/photo-enrichment'
photo = json.loads(yaml.safe_load((app / 'dashboard.yaml').read_text())['data']['photo-app.json'])
knowledge = json.loads(next(iter(yaml.safe_load((app / 'knowledge-index-dashboard.yaml').read_text())['data'].values())))
queries = []
for panel in photo['panels']:
    if panel['gridPos']['y'] < 37:
        queries.extend({'name': panel['title']+' '+target['refId'], 'expr': target['expr']} for target in panel.get('targets', []))
for panel in knowledge['panels']:
    if panel['type'] == 'nodeGraph':
        for target in panel['targets']:
            expr = target['expr'].replace('$__rate_interval', '5m').replace('$instance', '.*').replace('$pipeline_enricher', '.*')
            queries.append({'name': 'Value stream map '+target['refId'], 'expr': expr})
code = '''let raw='';for await(const c of process.stdin)raw+=c;
for(const q of JSON.parse(raw)){
const r=await fetch('http://kube-prometheus-stack-prometheus.monitoring.svc.cluster.local:9090/api/v1/query?query='+encodeURIComponent(q.expr));
const result=await r.json();console.log(JSON.stringify({name:q.name,status:result.status,error:result.error,count:result.data?.result?.length,values:result.data?.result?.slice(0,3).map(v=>({labels:v.metric,value:v.value[1]}))}));
}'''
result = subprocess.run(base+['-n','immich-pilot','exec','-i','deployment/immich-server','--','node','--input-type=module','-e',code],input=json.dumps(queries),text=True,capture_output=True,check=True)
failures = []
for line in result.stdout.splitlines():
    value = json.loads(line)
    print(json.dumps(value))
    if value['status'] != 'success' or value['count'] == 0:
        failures.append(value['name'])
if failures:
    print('Queries with errors or no samples: '+', '.join(failures), file=sys.stderr)
    sys.exit(1)
