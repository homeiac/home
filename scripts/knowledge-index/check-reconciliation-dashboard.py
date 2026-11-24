#!/usr/bin/env python3
"""Verify the GitOps reconciliation dashboard and its live Prometheus inputs."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.parse

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
    served_spec = importlib.util.spec_from_file_location('grafana_state', HERE / 'grafana-dashboard-state.py')
    served_module = importlib.util.module_from_spec(served_spec)
    served_spec.loader.exec_module(served_module)
    provisioning_deadline = time.monotonic() + (90 if args.reconcile else 0)
    while True:
        served = served_module.served_dashboard()['dashboard']
        if served['panels'] == expected['panels']:
            break
        if time.monotonic() >= provisioning_deadline:
            raise RuntimeError('Grafana is serving different panels despite the ConfigMap; check provisioning')
        time.sleep(3)
    print('Authenticated Grafana API serves the updated panels.')
    source = kubectl('-n', 'flux-system', 'get', 'gitrepository', 'photo-enrichment-preview', '-o', 'json')
    print('Flux source:', source['status']['artifact']['revision'])
    measurements = {}
    for panel in expected['panels']:
        if (panel['gridPos']['y'] >= module.RECONCILIATION_HEIGHT + 30
                and not any('knowledge_index_caption_completion{' in t['expr'] for t in panel.get('targets', []))):
            continue
        for target in panel.get('targets', []):
            expr = target['expr'].replace('$instance', '.*').replace('$__rate_interval', '5m')
            path = '/api/v1/namespaces/monitoring/services/http:kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?'
            result = kubectl('get', '--raw', path + urllib.parse.urlencode({'query': expr}))
            if result['status'] != 'success':
                raise RuntimeError('Prometheus query failed: ' + panel['title'])
            if not result['data']['result'] and panel['title'] in (
                    'Current speed · combined', 'Estimated time remaining', 'Estimated finish time'):
                print(panel['title'] + ': no estimate (freshness, throughput or pause guard)')
                continue
            if not result['data']['result']:
                raise RuntimeError('Missing live data: ' + panel['title'])
            values = [row['value'][1] for row in result['data']['result']]
            measurements[panel['title']] = values
            print(panel['title'] + ': ' + ', '.join(
                (row['metric'].get('kind', '') + ' ' + row['value'][1]).strip()
                for row in result['data']['result']))
    if measurements.get('Available pairs processed') == ['100']:
        for title in ('Estimated time remaining', 'Estimated finish time'):
            if measurements.get(title) != ['0']:
                raise RuntimeError('Completed batch must show Complete: ' + title)


if __name__ == '__main__':
    main()
