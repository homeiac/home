#!/usr/bin/env python3
"""Read current deduped video coverage from Prometheus without media paths."""
import json
import os
from pathlib import Path
import subprocess
import urllib.parse

os.environ.setdefault('KUBECONFIG', str(Path.home() / 'kubeconfig'))
query = 'max by(state) (knowledge_index_caption_completion{kind="video",model="local",scope="deduplicated"} and on(instance,job) (knowledge_index_exporter_success == 1) and on(instance,job) (time() - knowledge_index_last_run_timestamp_seconds < 900))'
path = '/api/v1/namespaces/monitoring/services/http:kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?'
result = json.loads(subprocess.check_output(['kubectl', 'get', '--raw', path + urllib.parse.urlencode({'query': query})]))
counts = {row['metric']['state']: int(float(row['value'][1])) for row in result['data']['result']}
if set(counts) != {'complete', 'remaining'}:
    raise RuntimeError('Fresh video coverage is unavailable')
counts['total'] = sum(counts.values())
counts['percent_complete'] = round(100 * counts['complete'] / counts['total'], 1) if counts['total'] else None
print(json.dumps(counts))
