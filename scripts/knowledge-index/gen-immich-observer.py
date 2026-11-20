#!/usr/bin/env python3
"""Generate private, read-only queue/VPA telemetry and bottleneck alerts (#217)."""
import hashlib
from pathlib import Path
import yaml

HERE = Path(__file__).resolve().parent
IMAGE = 'ghcr.io/immich-app/immich-server:v3.4.2@sha256:fc880c1bf665b4aab1e74c15e56ab871225989cd546536e6b77e771869af06bd'
NAME = 'immich-observer'
NS = 'immich-pilot'


def resources():
    source = (HERE / 'immich-queue-metrics.mjs').read_text()
    def obj(api, kind, spec=None, **extra):
        value = dict(apiVersion=api, kind=kind, metadata=dict(name=NAME, namespace=NS))
        if spec is not None:
            value['spec'] = spec
        value.update(extra)
        return value
    labels = {'app': NAME}
    yield obj('v1', 'ConfigMap', data={'immich-queue-metrics.mjs': source})
    yield obj('v1', 'ServiceAccount')
    yield obj('rbac.authorization.k8s.io/v1', 'Role', rules=[{
        'apiGroups': ['autoscaling.k8s.io'], 'resources': ['verticalpodautoscalers'],
        'resourceNames': ['immich-server', 'immich-machine-learning'], 'verbs': ['get']}])
    yield obj('rbac.authorization.k8s.io/v1', 'RoleBinding',
              roleRef={'apiGroup': 'rbac.authorization.k8s.io', 'kind': 'Role', 'name': NAME},
              subjects=[{'kind': 'ServiceAccount', 'name': NAME, 'namespace': NS}])
    yield obj('apps/v1', 'Deployment', {
        'replicas': 1, 'selector': {'matchLabels': labels}, 'template': {
            'metadata': {'labels': labels, 'annotations': {'checksum/config': hashlib.sha256(source.encode()).hexdigest()}},
            'spec': {'serviceAccountName': NAME,
                'nodeSelector': {'kubernetes.io/hostname': 'k3s-vm-pumped-piglet-gpu'},
                'securityContext': {'runAsNonRoot': True, 'runAsUser': 1000, 'seccompProfile': {'type': 'RuntimeDefault'}},
                'containers': [{'name': 'observer', 'image': IMAGE, 'command': ['node', '/observer/immich-queue-metrics.mjs'],
                    'ports': [{'name': 'metrics', 'containerPort': 9199}],
                    'resources': {'requests': {'cpu': '10m', 'memory': '64Mi'}, 'limits': {'cpu': '200m', 'memory': '128Mi'}},
                    'securityContext': {'allowPrivilegeEscalation': False, 'readOnlyRootFilesystem': True, 'capabilities': {'drop': ['ALL']}},
                    'volumeMounts': [{'name': 'code', 'mountPath': '/observer', 'readOnly': True}],
                    'readinessProbe': {'httpGet': {'path': '/healthz', 'port': 'metrics'}},
                    'livenessProbe': {'httpGet': {'path': '/healthz', 'port': 'metrics'}, 'initialDelaySeconds': 20}}],
                'volumes': [{'name': 'code', 'configMap': {'name': NAME}}]}}})
    service = obj('v1', 'Service', {'selector': labels, 'ports': [{'name': 'metrics', 'port': 9199, 'targetPort': 'metrics'}]})
    service['metadata']['labels'] = labels
    yield service
    monitor = obj('monitoring.coreos.com/v1', 'ServiceMonitor', {
        'selector': {'matchLabels': labels}, 'endpoints': [{'port': 'metrics', 'interval': '15s'}]})
    monitor['metadata']['labels'] = {'release': 'kube-prometheus-stack'}
    yield monitor
    from immich_dashboard import BACKLOG, RATE, THROTTLE
    rules = obj('monitoring.coreos.com/v1', 'PrometheusRule', {'groups': [{'name': 'immich.bottlenecks', 'rules': [
        {'alert': 'ImmichThumbnailQueueStalled', 'expr': f'({BACKLOG} > 0) and ({RATE} == 0)', 'for': '10m',
         'labels': {'severity': 'warning'}, 'annotations': {'summary': 'Immich thumbnail backlog is not draining',
            'description': 'Queued thumbnails with zero successful jobs for 10 minutes. Inspect CPU throttling, memory, worker errors and storage before retrying jobs.',
            'dashboard_url': 'https://grafana.app.home.panderosystems.com/d/photo-app/photo-app'}},
        {'alert': 'ImmichCpuThrottledWithThumbnailBacklog', 'expr': f'({THROTTLE} > 25) and on() ({BACKLOG} > 0)', 'for': '10m',
         'labels': {'severity': 'warning'}, 'annotations': {'summary': 'Immich CPU limit is throttling while thumbnails are queued',
            'description': 'More than 25% of CPU periods throttled for 10 minutes. Compare actual CPU, hard limits, VPA recommendations and node headroom.'}},
        {'alert': 'ImmichQueueTelemetryUnavailable', 'expr': 'min(immich_observer_source_up{source="queues"}) == 0 or absent(immich_observer_source_up{source="queues"})', 'for': '3m',
         'labels': {'severity': 'warning'}, 'annotations': {'summary': 'Immich queue depth is unknown',
            'description': 'Queue telemetry is unavailable. Missing data must not be read as an empty queue.'}}
    ]}]})
    rules['metadata']['labels'] = {'release': 'kube-prometheus-stack'}
    yield rules


if __name__ == '__main__':
    print(yaml.safe_dump_all(resources(), sort_keys=False), end='')
