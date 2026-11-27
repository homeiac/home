#!/usr/bin/env python3
"""Validate pet-tagger dashboard queries and optionally its live provisioning.

--queries-only works before deployment. Credentials stay inside the Grafana
sidecar; output contains aggregate metric values only.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import logging
import os
from pathlib import Path
import subprocess
import urllib.parse
import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DEST = ROOT / 'gitops/clusters/homelab/apps/photo-enrichment/immich-pet-tagger'
os.environ.setdefault('KUBECONFIG', str(Path.home() / 'kubeconfig'))


def kubectl(*args: str) -> dict:
    """Use the existing kubeconfig without logging authentication data."""
    return json.loads(subprocess.check_output(['kubectl', *args], text=True))


def served_dashboard(uid: str) -> dict:
    """Read Grafana using credentials retained inside its existing sidecar."""
    code = '''import base64,json,os,sys,urllib.request
credentials=(os.environ['REQ_USERNAME']+':'+os.environ['REQ_PASSWORD']).encode()
request=urllib.request.Request('http://localhost:3000/api/dashboards/uid/'+sys.argv[1],
    headers={'Authorization':'Basic '+base64.b64encode(credentials).decode(),'X-Grafana-Org-Id':'1'})
with urllib.request.urlopen(request,timeout=20) as response:
    print(response.read().decode())
'''
    return kubectl('-n', 'monitoring', 'exec', 'deployment/kube-prometheus-stack-grafana',
                   '-c', 'grafana-sc-dashboard', '--', 'python', '-c', code, uid)


def main() -> None:
    """Check generated parity, real PromQL and optional served dashboard parity."""
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--queries-only', action='store_true')
    parser.add_argument('--source', action='store_true', help='Inspect Prometheus discovery and scraping')
    args = parser.parse_args()
    if args.source:
        path = '/api/v1/namespaces/monitoring/services/http:kube-prometheus-stack-prometheus:9090/proxy/api/v1/targets'
        targets = kubectl('get', '--raw', path)['data']['activeTargets']
        found = [t for t in targets if t.get('labels', {}).get('service') == 'immich-pet-tagger-metrics']
        for target in found:
            logging.info('Collector target: health=%s lastScrape=%s error=%s',
                         target['health'], target['lastScrape'], target['lastError'])
        if not found:
            logging.info('Collector not yet discovered by Prometheus.')
        return
    spec = importlib.util.spec_from_file_location('generate', HERE / 'generate-dashboard.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    expected = module.dashboard()
    local = yaml.safe_load((DEST / 'dashboard.yaml').read_text())
    assert json.loads(local['data']['immich-waffles.json']) == expected
    assert list(yaml.safe_load_all((DEST / 'metrics.yaml').read_text())) == module.resources()
    logging.info('Generated dashboard and observer match committed manifests.')
    if not args.queries_only:
        actual = kubectl('-n', 'monitoring', 'get', 'configmap', 'grafana-dashboard-immich-waffles', '-o', 'json')
        assert json.loads(actual['data']['immich-waffles.json']) == expected
        served = served_dashboard('immich-waffles')
        assert served['meta']['provisioned'] is True
        assert served['dashboard']['panels'] == expected['panels']
        logging.info('Grafana serves exactly the GitOps-provisioned panels.')

    queries = [(panel['title'], target['expr']) for panel in expected['panels'] for target in panel.get('targets', [])]

    def query(item: tuple[str, str]) -> tuple[str, list]:
        title, expr = item
        path = '/api/v1/namespaces/monitoring/services/http:kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?'
        result = kubectl('get', '--raw', path + urllib.parse.urlencode({'query': expr}))
        assert result['status'] == 'success', title
        return title, result['data']['result']

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(query, queries))
    essential = {'Historical scan', 'Assets fetched', 'Waffles tags added', 'Failures reported',
                 'Last successful report', 'Status collector', 'Waffles references', 'Negative examples',
                 'Tagger available replicas', 'Prometheus scrape'}
    for title, rows in results:
        if not args.queries_only and title in essential:
            assert rows, 'Missing telemetry: ' + title
            if title in ('Status collector', 'Prometheus scrape'):
                assert rows[0]['value'][1] == '1', 'Unhealthy: ' + title
        values = ', '.join(row['value'][1] for row in rows)
        logging.info('%s: %s', title, values or 'no sample (conditional or unavailable)')
    logging.info('Validated %d live PromQL expressions.', len(queries))


if __name__ == '__main__':
    main()
