#!/usr/bin/env python3
"""Read the dashboard Grafana serves using the sidecar's existing local credentials."""
import json
import os
from pathlib import Path
import subprocess


def served_dashboard() -> dict:
    """Keep credentials inside the pod; return only dashboard JSON over kubectl."""
    os.environ.setdefault('KUBECONFIG', str(Path.home()/'kubeconfig'))
    code='''import base64,json,os,urllib.request
credentials=(os.environ['REQ_USERNAME']+':'+os.environ['REQ_PASSWORD']).encode()
request=urllib.request.Request('http://localhost:3000/api/dashboards/uid/knowledge-index',
    headers={'Authorization':'Basic '+base64.b64encode(credentials).decode(),'X-Grafana-Org-Id':'1'})
with urllib.request.urlopen(request,timeout=20) as response:
    print(response.read().decode())
'''
    return json.loads(subprocess.check_output(['kubectl','-n','monitoring','exec','-i',
        'deployment/kube-prometheus-stack-grafana','-c','grafana-sc-dashboard','--','python','-c',code],text=True))


if __name__=='__main__':
    value=served_dashboard();dashboard=value['dashboard']
    print(json.dumps(dict(uid=dashboard['uid'],version=dashboard.get('version'),meta=value['meta'],
        panels=len(dashboard['panels']),first_panels=[p['title'] for p in dashboard['panels'][:8]]),indent=2))
