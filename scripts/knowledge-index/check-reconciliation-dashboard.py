#!/usr/bin/env python3
"""Verify the GitOps reconciliation dashboard and its live Prometheus inputs."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = Path(__file__).resolve().parent


def kubectl(*args: str) -> dict:
    """Read cluster JSON using the existing user context."""
    return json.loads(subprocess.check_output(['kubectl', *args], text=True))


def main() -> None:
    """Optionally reconcile the existing Flux source, then compare provisioned JSON."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reconcile', action='store_true')
    args = parser.parse_args()
    os.environ.setdefault('KUBECONFIG', str(Path.home() / 'kubeconfig'))
    if args.reconcile:
        revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=HERE, text=True).strip()
        stamp = str(time.time_ns())
        for kind in ('gitrepository', 'kustomization'):
            subprocess.run(['kubectl', '-n', 'flux-system', 'annotate', kind,
                            'photo-enrichment-preview', '--overwrite',
                            'reconcile.fluxcd.io/requestedAt=' + stamp], check=True)
        deadline = time.monotonic() + 180
        while True:
            applied = kubectl('-n', 'flux-system', 'get', 'kustomization', 'photo-enrichment-preview', '-o', 'json')['status']
            ready = any(c['type'] == 'Ready' and c['status'] == 'True' for c in applied.get('conditions', []))
            if ready and applied.get('lastAppliedRevision', '').endswith(revision):
                break
            if time.monotonic() >= deadline:
                raise RuntimeError('Flux has not applied this commit within three minutes')
            time.sleep(3)
    spec = importlib.util.spec_from_file_location('dashboard', HERE / 'gen-dashboard.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    expected = module.dashboard()
    resource = kubectl('-n', 'monitoring', 'get', 'configmap',
                       'grafana-dashboard-knowledge-index', '-o', 'json')
    actual = json.loads(resource['data']['knowledge-index.json'])
    if actual != expected:
        raise RuntimeError('Live ConfigMap differs from the generated dashboard')
    print('Live dashboard ConfigMap matches Git exactly.')
    source = kubectl('-n', 'flux-system', 'get', 'gitrepository', 'photo-enrichment-preview', '-o', 'json')
    print('Flux source:', source['status']['artifact']['revision'])
    for panel in expected['panels']:
        if panel['gridPos']['y'] >= module.RECONCILIATION_HEIGHT:
            continue
        for target in panel.get('targets', []):
            expr = target['expr'].replace('$instance', '.*').replace('$__rate_interval', '5m')
            path = '/api/v1/namespaces/monitoring/services/http:kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?'
            result = kubectl('get', '--raw', path + urllib.parse.urlencode({'query': expr}))
            if result['status'] != 'success' or not result['data']['result']:
                raise RuntimeError('Missing live data: ' + panel['title'])
            values = [row['value'][1] for row in result['data']['result']]
            print(panel['title'] + ': ' + ', '.join(values))
    # Anonymous dashboard read when enabled; never fetch or print credentials.
    url = 'https://grafana.app.home.panderosystems.com/api/dashboards/uid/knowledge-index'
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            served = json.load(response)['dashboard']
        if served['panels'] != expected['panels']:
            raise RuntimeError('Grafana has not loaded the updated panels yet')
        print('Grafana API serves the updated panels.')
    except urllib.error.HTTPError as exc:
        if exc.code not in (401, 403):
            raise
        print('Grafana API requires sign-in; Flux ConfigMap and live metrics verified.')


if __name__ == '__main__':
    main()
