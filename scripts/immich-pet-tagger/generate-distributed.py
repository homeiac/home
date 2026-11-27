#!/usr/bin/env python3
"""Generate PG queue, CPU workers, private gateway and VPA recommendation policies."""
import hashlib
from pathlib import Path
import yaml

HERE = Path(__file__).resolve().parent
DEST = HERE.parents[1] / 'gitops/clusters/homelab/apps/photo-enrichment/immich-pet-tagger'
NODE_IMAGE = 'ghcr.io/immich-app/immich-server:v3.4.2@sha256:fc880c1bf665b4aab1e74c15e56ab871225989cd546536e6b77e771869af06bd'
CPU_IMAGE = 'ghcr.io/tedornitier/immich-pet-tagger:v1.10.0-cpu@sha256:535b4664511db709b1069a7eac789339af05264585511feeea24f68430edf7e6'
SECURITY = {'runAsNonRoot': True, 'runAsUser': 1000, 'runAsGroup': 1000, 'fsGroup': 1000, 'seccompProfile': {'type': 'RuntimeDefault'}}
CONTAINER_SECURITY = {'readOnlyRootFilesystem': True, 'allowPrivilegeEscalation': False, 'capabilities': {'drop': ['ALL']}}


def env(name, value=None, secret=None, key=None):
    return {'name': name, **({'value': value} if value is not None else {'valueFrom': {'secretKeyRef': {'name': secret, 'key': key}}})}


def obj(kind, name, namespace='immich-pilot', api='v1', **values):
    return {'apiVersion': api, 'kind': kind, 'metadata': {'name': name, 'namespace': namespace}, **values}


def resources():
    files = {name: (HERE / name).read_text() for name in ['schema.sql', 'bootstrap.mjs', 'queue-core.mjs', 'coordinator.mjs', 'discovery.mjs', 'distributed-worker.py', 'supervisor.py', 'burst-worker.py', 'burst-supervisor.py', 'burst_guard.py', 'test-queue.mjs']}
    digest = hashlib.sha256(''.join(files.values()).encode()).hexdigest()
    for namespace in ('database', 'immich-pilot'):
        yield obj('ConfigMap', 'waffles-code', namespace, data=files)
    pg = [env('PGHOST', 'postgres-postgresql.database.svc.cluster.local'), env('PGDATABASE', 'photo_enrichment')]
    base = {'automountServiceAccountToken': False, 'securityContext': SECURITY,
            'volumes': [{'name': 'code', 'configMap': {'name': 'waffles-code'}}]}
    container = {'name': 'queue', 'image': NODE_IMAGE, 'securityContext': CONTAINER_SECURITY,
                 'volumeMounts': [{'name': 'code', 'mountPath': '/code', 'readOnly': True}],
                 'resources': {'requests': {'cpu': '25m', 'memory': '64Mi'}, 'limits': {'cpu': '500m', 'memory': '256Mi'}}}
    yield obj('Job', 'waffles-schema-v5', 'database', api='batch/v1', spec={'backoffLimit': 3, 'template': {'spec': {
        **base, 'restartPolicy': 'Never', 'containers': [{**container, 'command': ['node', '/code/bootstrap.mjs'],
         'env': pg + [env('PGUSER', 'postgres'), env('PGPASSWORD', secret='postgres-credentials', key='postgres-password'), env('ROLE_PASSWORD', secret='waffles-queue', key='password')]}]}}})
    app = {'app': 'waffles-queue'}
    yield obj('Deployment', 'waffles-queue', api='apps/v1', spec={'replicas': 1, 'strategy': {'type': 'Recreate'}, 'selector': {'matchLabels': app},
        'template': {'metadata': {'labels': app, 'annotations': {'checksum/code': digest}}, 'spec': {**base,
            'nodeSelector': {'kubernetes.io/hostname': 'k3s-vm-still-fawn'},
            'containers': [{**container, 'command': ['node', '/code/coordinator.mjs'],
                'env': pg + [env('PGUSER', 'waffles_worker'), env('PGPASSWORD', secret='waffles-queue', key='password'),
                           env('WORKER_TOKEN', secret='waffles-queue', key='worker-token'), env('ADMIN_TOKEN', secret='waffles-queue', key='admin-token'),
                           env('IMMICH_API_KEY', secret='immich-pet-tagger', key='api-key')],
                'ports': [{'name': 'http', 'containerPort': 9200}],
                'readinessProbe': {'httpGet': {'path': '/healthz', 'port': 'http'}, 'periodSeconds': 5},
                'livenessProbe': {'tcpSocket': {'port': 'http'}, 'initialDelaySeconds': 30}}]}}})
    service = obj('Service', 'waffles-queue', spec={'selector': app, 'ports': [{'name': 'http', 'port': 9200, 'targetPort': 'http'}]})
    service['metadata']['labels'] = app
    yield service
    monitor = obj('ServiceMonitor', 'waffles-queue', api='monitoring.coreos.com/v1', spec={'selector': {'matchLabels': app}, 'endpoints': [{'port': 'http', 'interval': '15s'}]})
    monitor['metadata']['labels'] = {'release': 'kube-prometheus-stack'}
    yield monitor
    yield obj('IngressRoute', 'waffles-queue', api='traefik.io/v1alpha1', spec={'entryPoints': ['websecure'], 'routes': [{
        'match': 'Host(`pets-queue.app.home.panderosystems.com`)', 'kind': 'Rule', 'middlewares': [{'name': 'private'}],
        'services': [{'name': 'waffles-queue', 'port': 9200}]}], 'tls': {}})
    # Baseline pods are preserved verbatim in baseline.yaml. Only additional
    # capacity rolls when this generated burst controller changes.
    for worker, cpu, memory in [('still-fawn', '3', '6Gi'), ('pve', '1', '1536Mi')]:
        name = 'waffles-burst-' + worker
        labels = {'app': name, 'waffles-worker': worker, 'waffles-pool': 'burst'}
        pvc = obj('PersistentVolumeClaim', name, spec={'accessModes': ['ReadWriteOnce'], 'storageClassName': 'local-path', 'resources': {'requests': {'storage': '3Gi'}}})
        pvc['metadata']['annotations'] = {'kustomize.toolkit.fluxcd.io/prune': 'disabled'}
        yield pvc
        yield obj('Deployment', name, api='apps/v1', spec={'replicas': 1, 'strategy': {'type': 'Recreate'}, 'selector': {'matchLabels': labels},
            'template': {'metadata': {'labels': labels, 'annotations': {'checksum/code': digest}}, 'spec': {**base,
                'nodeSelector': {'kubernetes.io/hostname': 'k3s-vm-' + worker},
                'terminationGracePeriodSeconds': 90,
                'containers': [{'name': 'worker', 'image': CPU_IMAGE, 'command': ['python', '-B', '/code/burst-supervisor.py'],
                    'env': [env('QUEUE_URL', 'http://waffles-queue.immich-pilot.svc.cluster.local:9200'), env('WORKER_NAME', worker),
                            env('WORKER_TOKEN_FILE', '/credentials/worker-token'), env('MODEL_WORKERS', '1'), env('SCAN_WORKERS', '1'),
                            env('OMP_NUM_THREADS', '2'), env('MKL_NUM_THREADS', '2'), env('OPENBLAS_NUM_THREADS', '2')],
                    'resources': {'requests': {'cpu': '100m', 'memory': '512Mi'}, 'limits': {'cpu': cpu, 'memory': memory}},
                    'securityContext': CONTAINER_SECURITY,
                    'volumeMounts': [{'name': 'code', 'mountPath': '/code', 'readOnly': True}, {'name': 'data', 'mountPath': '/data'},
                                     {'name': 'credentials', 'mountPath': '/credentials', 'readOnly': True}, {'name': 'tmp', 'mountPath': '/tmp'}]}],
                'volumes': base['volumes'] + [{'name': 'data', 'persistentVolumeClaim': {'claimName': name}},
                                            {'name': 'credentials', 'secret': {'secretName': 'waffles-queue', 'items': [{'key': 'worker-token', 'path': 'worker-token'}]}},
                                            {'name': 'tmp', 'emptyDir': {'sizeLimit': '256Mi'}}]}}})
    for name, container_name, cpu, memory in [('immich-pet-tagger', 'tagger', '2', '4Gi'), ('waffles-burst-still-fawn', 'worker', '3', '6Gi'), ('waffles-burst-pve', 'worker', '1', '1536Mi')]:
        yield obj('VerticalPodAutoscaler', name, api='autoscaling.k8s.io/v1', spec={
            'targetRef': {'apiVersion': 'apps/v1', 'kind': 'Deployment', 'name': name},
            'updatePolicy': {'updateMode': 'Off'}, 'resourcePolicy': {'containerPolicies': [{
                'containerName': container_name, 'controlledResources': ['cpu', 'memory'], 'controlledValues': 'RequestsOnly',
                'minAllowed': {'cpu': '100m', 'memory': '256Mi'}, 'maxAllowed': {'cpu': cpu, 'memory': memory}}]}})


if __name__ == '__main__':
    (DEST / 'distributed.yaml').write_text(yaml.safe_dump_all(resources(), sort_keys=False))
