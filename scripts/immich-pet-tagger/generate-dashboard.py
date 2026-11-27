#!/usr/bin/env python3
"""Generate the dedicated Waffles dashboard and independent read-only observer."""
import hashlib
import json
from pathlib import Path
import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DEST = ROOT / 'gitops/clusters/homelab/apps/photo-enrichment/immich-pet-tagger'
DS = {'type': 'prometheus', 'uid': 'prometheus'}
M = 'immich_pet_tagger_'
FRESH = (f'(max({M}source_up) == 1) and on() '
         f'(time() - max({M}last_success_timestamp_seconds) < 60)')
RUNNING = f'(max({M}scan_state{{scope="manual"}}) == 1)'


def live(expr: str) -> str:
    """Hide unavailable or stale status rather than making it look successful."""
    return f'({expr}) and on() ({FRESH})'


def count(outcome: str) -> str:
    """Return one outcome, without summing incompatible crop and asset counts."""
    return live(f'max({M}scan_items{{scope="manual",outcome="{outcome}"}})')


def dashboard() -> dict:
    """Build an overview inspired by Knowledge Index, followed by scoped details."""
    panels = []

    def panel(title, exprs, x, y, w=4, h=4, kind='stat', unit='short', description='', mappings=None):
        targets = [{'refId': chr(65 + i), 'expr': expr, 'legendFormat': label,
                    'instant': kind == 'stat', 'range': kind != 'stat'}
                   for i, (expr, label) in enumerate(exprs)]
        defaults = {'unit': unit, 'noValue': 'Awaiting telemetry', 'decimals': 0,
                    'color': {'mode': 'palette-classic'},
                    'thresholds': {'mode': 'absolute', 'steps': [{'color': 'green', 'value': None}]}}
        if mappings:
            defaults['mappings'] = [{'type': 'value', 'options': mappings}]
            defaults['color'] = {'mode': 'thresholds'}
        options = ({'reduceOptions': {'calcs': ['lastNotNull']}, 'graphMode': 'none',
                    'colorMode': 'value', 'textMode': 'value'} if kind == 'stat'
                   else {'legend': {'displayMode': 'list', 'placement': 'bottom'}, 'tooltip': {'mode': 'multi'}})
        p = {'id': len(panels) + 1, 'type': kind, 'title': title, 'datasource': DS,
             'gridPos': {'x': x, 'y': y, 'w': w, 'h': h}, 'description': description,
             'targets': targets, 'fieldConfig': {'defaults': defaults, 'overrides': []}, 'options': options}
        panels.append(p)
        return p

    states = {str(i): {'text': label, 'color': color} for i, label, color in
              [(0, 'No manual scan', 'gray'), (1, 'Running', 'blue'), (2, 'Complete', 'green'),
               (3, 'Stopped', 'orange'), (4, 'Error', 'red'), (5, 'Unknown', 'orange')]}
    panel('Historical scan', [(live(f'max({M}scan_state{{scope="manual"}})'), '')], 0, 0,
          mappings=states, description='Latest manual scan result. Independent of the automatic hourly cycle. Missing or stale telemetry is never reported as complete.')
    panel('Assets fetched', [(count('fetched'), '')], 4, 0,
          description='Assets enumerated for the current manual date window, not assets processed or remaining.')
    panel('Waffles tags added', [(count('added'), '')], 8, 0,
          description='New face assignments in this manual scan. Waffles is the only enrolled pet. Excludes the initial reference tags and earlier scans.')
    p = panel('Failures reported', [(count('failed'), '')], 12, 0,
              description='Upstream failed outcome count; can include inference, thumbnail processing or face-write failures. Not an error percentage.')
    p['fieldConfig']['defaults'].update(color={'mode': 'thresholds'}, thresholds={'mode': 'absolute', 'steps': [{'color': 'green', 'value': None}, {'color': 'red', 'value': 1}]})
    panel('Scan elapsed', [(live(f'(time() - max({M}scan_started_at_timestamp_seconds{{scope="manual"}})) and on() {RUNNING}'), '')], 16, 0,
          unit='s', description='Wall time since the running manual scan started, including model preparation. Not an ETA.')
    p = panel('Last successful report', [(f'time() - max({M}last_success_timestamp_seconds > 0)', '')], 20, 0,
              unit='s', description='Age of the last successful status collection. Observer polls every 15 seconds. Measures telemetry freshness, not inference progress.')
    p['fieldConfig']['defaults'].update(color={'mode': 'thresholds'}, thresholds={'mode': 'absolute', 'steps': [{'color': 'green', 'value': None}, {'color': 'orange', 'value': 60}, {'color': 'red', 'value': 180}]})

    panel('Current photo date (UTC)', [(live(f'max({M}photo_date_timestamp_seconds{{scope="manual"}}) * 1000'), '')], 0, 4, w=6,
          unit='dateTimeAsIso', description='Taken date of the most recently started photo. Concurrent workers can move this backward; it is not a completed-through watermark.')
    panel('Already tagged matches', [(count('already_tagged'), '')], 6, 4, w=6,
          description='Matching crops skipped because the person was already assigned, including duplicate matches within one photo. Not distinct photos.')
    panel('Missing thumbnails', [(count('no_thumb'), '')], 12, 4, w=6,
          description='Assets where the upstream thumbnail fetch returned no image.')
    panel('Review assets after completion', [(live(f'max({M}review_assets)'), '')], 18, 4, w=6,
          description='Available only after the manual scan completes. v1.10.0 overwrites live low-confidence counts with an unpopulated review list during a scan; do not interpret that as zero.')['fieldConfig']['defaults']['noValue'] = 'Available after scan'

    panels.append({'id': len(panels) + 1, 'type': 'text', 'title': 'Reading this scan',
        'gridPos': {'x': 0, 'y': 8, 'w': 24, 'h': 3}, 'options': {'mode': 'markdown',
        'content': '**Waffles only · CPU inference · private homelab**  \n'
        'Immich photos → animal detection → embedding + Waffles classifier → Immich People and `Pets/Review`. '
        '**Fetched is the scan scope, not completed work.** Outcomes mix crops and assets; they cannot be summed into a completion percentage or ETA. '
        'A low match rate is expected in a whole-library scan. Model accuracy requires reviewed photos, not dashboard counts.'}})

    # Same Prometheus table-to-nodeGraph pattern used by Knowledge Index.
    def label(expr, fields):
        for key, value in fields:
            expr = f'label_replace(({expr}), "{key}", "{value}", "", "")'
        return expr
    nodes = [('photos', 'Photos fetched', count('fetched')),
             ('references', 'Waffles references', live(f'max({M}references)')),
             ('negatives', 'Negative examples', live(f'max({M}negatives)')),
             ('scan', 'Detection + classifier', live(f'max({M}scan_state{{scope="manual"}})')),
             ('tags', 'New face assignments', count('added')),
             ('unknown', 'Unknown crops', count('unknown')),
             ('failed', 'Failed outcomes', count('failed'))]
    edges = [('photos', 'scan'), ('references', 'scan'), ('negatives', 'scan'),
             ('scan', 'tags'), ('scan', 'unknown'), ('scan', 'failed')]
    graph = {'id': len(panels) + 1, 'type': 'nodeGraph', 'title': 'Waffles recognition pipeline',
             'datasource': DS, 'gridPos': {'x': 0, 'y': 11, 'w': 24, 'h': 9},
             'description': 'Logical flow, not measured transfer rates or phase timings. Detection/classifier value is scan state: 1 running, 2 completed. Other nodes show their named counts; crops and assets are different units.',
             'targets': [{'refId': 'nodes', 'expr': ' or '.join(label(expr, [('id', key), ('title', title)]) for key, title, expr in nodes),
                          'format': 'table', 'instant': True, 'range': False},
                         {'refId': 'edges', 'expr': ' or '.join(label('vector(1)', [('id', a+'_'+b), ('source', a), ('target', b)]) for a, b in edges),
                          'format': 'table', 'instant': True, 'range': False}],
             'options': {'nodes': {'mainStatUnit': 'short'}},
             'transformations': [
                 {'id': 'calculateField', 'filter': {'id': 'byRefId', 'options': 'nodes'}, 'options': {'mode': 'reduceRow', 'reduce': {'reducer': 'sum', 'include': ['Value', 'Value #nodes']}, 'alias': 'mainstat'}},
                 {'id': 'organize', 'filter': {'id': 'byRefId', 'options': 'nodes'}, 'options': {'excludeByName': {'Time': True, 'Value': True, 'Value #nodes': True}}},
                 {'id': 'organize', 'filter': {'id': 'byRefId', 'options': 'edges'}, 'options': {'excludeByName': {'Time': True, 'Value': True, 'Value #edges': True}}}]}
    panels.append(graph)
    pace = live(f'(max(clamp_min(deriv({M}scan_items{{scope="manual",outcome="added"}}[5m]), 0) '
                f'and on(job,instance,scope) (changes({M}scan_started_at_timestamp_seconds{{scope="manual"}}[5m]) == 0)) * 60) '
                f'and on() {RUNNING}')
    panel('New Waffles assignments / minute', [(pace, 'Assignments/min')], 0, 20, 12, 7, 'timeseries',
          description='Five-minute slope of the per-scan added gauge. Suppressed across observed scan-start changes, outside running scans and when telemetry is stale. Measures tag writes, not photo processing speed.')['fieldConfig']['defaults']['decimals'] = 2
    panel('Manual scan outcomes', [(count(outcome), name) for outcome, name in
          [('added', 'Added assignments'), ('already_tagged', 'Already tagged crops'), ('unknown', 'Unknown crops'), ('failed', 'Failed outcomes'), ('no_thumb', 'Missing thumbnail assets')]],
          12, 20, 12, 7, 'timeseries', description='Independent per-scan gauges; reset on new scans. Not a stacked or mutually exclusive count of photos.')

    app = 'namespace="immich-pilot",container="tagger",pod=~"immich-pet-tagger-[a-f0-9]+-.*"'
    cpu = f'sum(rate(container_cpu_usage_seconds_total{{{app}}}[5m]))'
    memory = f'sum(container_memory_working_set_bytes{{{app}}})'
    limits = 'namespace="immich-pilot",container="tagger"'
    panel('Tagger CPU · usage and limit', [(cpu, 'CPU used'), (f'sum(kube_pod_container_resource_limits{{{limits},resource="cpu"}})', 'CPU limit')], 0, 27, 12, 7, 'timeseries', 'cores')['fieldConfig']['defaults']['decimals'] = 2
    panel('Tagger memory · working set and limit', [(memory, 'Working set'), (f'sum(kube_pod_container_resource_limits{{{limits},resource="memory"}})', 'Memory limit')], 12, 27, 12, 7, 'timeseries', 'bytes')
    panel('CPU throttled scheduling periods', [(f'100 * sum(rate(container_cpu_cfs_throttled_periods_total{{{app}}}[5m])) / sum(rate(container_cpu_cfs_periods_total{{{app}}}[5m]))', 'Throttled periods')],
          0, 34, 8, 7, 'timeseries', 'percent', description='Fraction of scheduling periods throttled, not CPU utilization. Correlate with usage and recognition progress.')
    panel('Tagger restarts', [(f'max(kube_pod_container_status_restarts_total{{{app}}})', 'Restarts')], 8, 34, 8, 7, 'timeseries', description='A restart interrupts the in-memory manual backfill. A no-manual-scan state after restart does not prove completion.')
    panel('Storage · backing filesystem', [('max(kubelet_volume_stats_used_bytes{namespace="immich-pilot",persistentvolumeclaim="immich-pet-tagger"})', 'Used'),
          ('max(kubelet_volume_stats_capacity_bytes{namespace="immich-pilot",persistentvolumeclaim="immich-pet-tagger"})', 'Capacity')], 16, 34, 8, 7, 'timeseries', 'bytes',
          description='Kubelet reports the entire backing filesystem for this local-path PVC. These are not tagger-directory bytes or an enforced 5 GiB quota. Absence means unreported, not empty.')
    health = {'0': {'text': 'Unavailable', 'color': 'red'}, '1': {'text': 'Healthy', 'color': 'green'}}
    panel('Status collector', [(f'max({M}source_up) and on() (time() - max({M}collection_timestamp_seconds) < 60)', '')], 0, 41, w=6, mappings=health)
    panel('Tagger available replicas', [('max(kube_deployment_status_replicas_available{namespace="immich-pilot",deployment="immich-pet-tagger"})', '')], 6, 41, w=6)
    panel('Waffles references', [(live(f'max({M}references)'), '')], 12, 41, w=6)
    panel('Negative examples', [(live(f'max({M}negatives)'), '')], 18, 41, w=6)
    cycle_states = {**states, '0': {'text': 'No cycle', 'color': 'gray'}, '2': {'text': 'Idle', 'color': 'green'}}
    panel('Latest cycle state', [(live(f'max({M}scan_state{{scope="latest_cycle"}})'), '')], 0, 45, w=6, mappings=cycle_states,
          description='Shared upstream poll status includes manual and automatic scans. Running does not mean two scans are executing; they share a lock.')
    panel('Latest cycle assignments', [(live(f'max({M}scan_items{{scope="latest_cycle",outcome="added"}})'), '')], 6, 45, w=6,
          description='Final count from the latest completed cycle. Not a lifetime total; can overlap the manual scan. Upstream omits it while running.')
    panel('Latest cycle final report', [(live(f'max({M}scan_ran_at_timestamp_seconds{{scope="latest_cycle"}}) * 1000'), '')], 12, 45, w=6, unit='dateTimeAsIso')
    panel('Prometheus scrape', [('max(up{namespace="immich-pilot",service="immich-pet-tagger-metrics"})', '')], 18, 45, w=6, mappings=health)
    return {'uid': 'immich-waffles', 'title': 'Waffles · Immich Pet Tagger', 'schemaVersion': 39,
            'version': 1, 'editable': False, 'tags': ['immich', 'waffles', 'pets', 'gitops'],
            'timezone': 'utc', 'refresh': '30s', 'time': {'from': 'now-6h', 'to': 'now'},
            'links': [{'title': 'Pet Tagger · scan and review', 'url': 'https://pets.app.home.panderosystems.com', 'type': 'link', 'targetBlank': True},
                      {'title': 'Immich', 'url': 'https://immich.app.home.panderosystems.com', 'type': 'link', 'targetBlank': True},
                      {'title': 'Knowledge Index', 'url': '/d/knowledge-index/knowledge-index', 'type': 'link'}],
            'panels': panels}


def resources() -> list[dict]:
    """Use the already verified Python image; the observer imports no ML libraries."""
    code = (HERE / 'metrics.py').read_text()
    app = {'app': 'immich-pet-tagger-metrics'}
    meta = {'name': 'immich-pet-tagger-metrics', 'namespace': 'immich-pilot'}
    image = next(d for d in yaml.safe_load_all((DEST / 'resources.yaml').read_text()) if d['kind'] == 'Deployment')['spec']['template']['spec']['containers'][0]['image']
    return [
        {'apiVersion': 'v1', 'kind': 'ConfigMap', 'metadata': meta, 'data': {'metrics.py': code}},
        {'apiVersion': 'apps/v1', 'kind': 'Deployment', 'metadata': meta,
         'spec': {'replicas': 1, 'selector': {'matchLabels': app}, 'template': {
             'metadata': {'labels': app, 'annotations': {'checksum/config': hashlib.sha256(code.encode()).hexdigest()}},
             'spec': {'automountServiceAccountToken': False,
                      'nodeSelector': {'kubernetes.io/hostname': 'k3s-vm-still-fawn'},
                      'securityContext': {'runAsNonRoot': True, 'runAsUser': 1000, 'runAsGroup': 1000, 'seccompProfile': {'type': 'RuntimeDefault'}},
                      'containers': [{'name': 'metrics', 'image': image, 'command': ['python', '-B', '/observer/metrics.py'],
                                      'workingDir': '/tmp', 'ports': [{'name': 'metrics', 'containerPort': 9198}],
                                      'resources': {'requests': {'cpu': '10m', 'memory': '32Mi'}, 'limits': {'cpu': '100m', 'memory': '96Mi'}},
                                      'securityContext': {'allowPrivilegeEscalation': False, 'readOnlyRootFilesystem': True, 'capabilities': {'drop': ['ALL']}},
                                      'volumeMounts': [{'name': 'code', 'mountPath': '/observer', 'readOnly': True}],
                                      'readinessProbe': {'httpGet': {'path': '/healthz', 'port': 'metrics'}},
                                      'livenessProbe': {'httpGet': {'path': '/healthz', 'port': 'metrics'}, 'initialDelaySeconds': 10}}],
                      'volumes': [{'name': 'code', 'configMap': {'name': meta['name']}}]}}}},
        {'apiVersion': 'v1', 'kind': 'Service', 'metadata': {**meta, 'labels': app},
         'spec': {'selector': app, 'ports': [{'name': 'metrics', 'port': 9198, 'targetPort': 'metrics'}]}},
        {'apiVersion': 'monitoring.coreos.com/v1', 'kind': 'ServiceMonitor', 'metadata': {**meta, 'labels': {'release': 'kube-prometheus-stack'}},
         'spec': {'selector': {'matchLabels': app}, 'endpoints': [{'port': 'metrics', 'interval': '15s'}]}},
    ]


def main() -> None:
    """Write deterministic, reviewable manifests without changing the tagger pod."""
    (DEST / 'metrics.yaml').write_text(yaml.safe_dump_all(resources(), sort_keys=False))
    encoded = json.dumps(dashboard(), indent=2)
    header = ('apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: grafana-dashboard-immich-waffles\n'
              '  namespace: monitoring\n  labels:\n    grafana_dashboard: "1"\n'
              '  annotations:\n    grafana_folder: Homelab\ndata:\n  immich-waffles.json: |-\n')
    (DEST / 'dashboard.yaml').write_text(header + '\n'.join('    ' + line for line in encoded.splitlines()) + '\n')


if __name__ == '__main__':
    main()
