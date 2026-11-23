#!/usr/bin/env python3
"""Render the Flux ConfigMap, one-shot rollout Job and periodic drift repair Job."""
import hashlib
import json
from pathlib import Path
import sys
import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
OUT = REPO / 'gitops/clusters/homelab/apps/photo-enrichment/caption-worker'
IMAGE = 'alpine/git:v2.49.1@sha256:53a6239398162098fed2f49a46512f9cbba9e3f31b9f2cea4fa90129ee069a99'


def resources() -> list[dict]:
    """Bundle code from its canonical source and name the rollout by content hash."""
    bundle = {name: (HERE.parent / 'enrichers' / name).read_text()
              for name in ('media_summary.py', 'pipeline_metrics.py', 'summary_cache.py')}
    bundle.update({name: (HERE / name).read_text()
                   for name in ('run.py', 'config.json', 'knowledge-index-enrich.service')})
    bundle['dispatch-policy.json'] = (HERE.parent / 'bonsai-dispatch-policy.json').read_text()
    for name in ('export-metrics.py', 'caption_completion.py'):
        bundle[name] = (HERE.parent / name).read_text()
    raw = json.dumps(bundle, sort_keys=True)
    revision = hashlib.sha256(raw.encode()).hexdigest()[:12]
    cm = 'caption-worker-' + revision
    pod = {'metadata': {'labels': {'app': 'caption-worker-installer'}}, 'spec': {
        'restartPolicy': 'Never', 'automountServiceAccountToken': False,
        'nodeSelector': {'kubernetes.io/arch': 'amd64'},
        'securityContext': {'runAsNonRoot': True, 'runAsUser': 65534, 'runAsGroup': 65534, 'fsGroup': 65534,
                            'seccompProfile': {'type': 'RuntimeDefault'}},
        'containers': [{'name': 'install', 'image': IMAGE,
            'command': ['/bin/sh', '-ec',
                'cp /credentials/id_ed25519 /work/deploy.key; chmod 600 /work/deploy.key; '
                'exec ssh -T -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=15 '
                '-o ServerAliveCountMax=3 -o StrictHostKeyChecking=yes '
                '-o UserKnownHostsFile=/credentials/known_hosts -i /work/deploy.key '
                'root@pumped-piglet.maas caption-reconcile < /bundle/bundle.json'],
            'securityContext': {'allowPrivilegeEscalation': False, 'readOnlyRootFilesystem': True,
                                'capabilities': {'drop': ['ALL']}},
            'resources': {'requests': {'cpu': '10m', 'memory': '32Mi'}, 'limits': {'cpu': '100m', 'memory': '128Mi'}},
            'volumeMounts': [{'name': 'bundle', 'mountPath': '/bundle', 'readOnly': True},
                             {'name': 'credentials', 'mountPath': '/credentials', 'readOnly': True},
                             {'name': 'work', 'mountPath': '/work'}]}],
        'volumes': [{'name': 'bundle', 'configMap': {'name': cm}},
                    {'name': 'credentials', 'secret': {'secretName': 'caption-worker-deploy', 'defaultMode': 0o440}},
                    {'name': 'work', 'emptyDir': {'medium': 'Memory', 'sizeLimit': '1Mi'}}]}}
    job = {'backoffLimit': 2, 'activeDeadlineSeconds': 240, 'template': pod}
    return [
        {'apiVersion': 'v1', 'kind': 'ConfigMap', 'metadata': {'name': cm, 'namespace': 'monitoring'},
         'data': {'bundle.json': raw}},
        {'apiVersion': 'batch/v1', 'kind': 'Job', 'metadata': {'name': cm, 'namespace': 'monitoring'}, 'spec': job},
        {'apiVersion': 'batch/v1', 'kind': 'CronJob',
         'metadata': {'name': 'caption-worker-reconcile', 'namespace': 'monitoring'},
         'spec': {'schedule': '*/5 * * * *', 'concurrencyPolicy': 'Forbid', 'startingDeadlineSeconds': 240,
                  'successfulJobsHistoryLimit': 1, 'failedJobsHistoryLimit': 2, 'jobTemplate': {'spec': job}}},
    ]


def main() -> None:
    """Write deterministic manifests, or check that committed output is current."""
    text = yaml.safe_dump_all(resources(), sort_keys=False, width=120)
    target = OUT / 'resources.yaml'
    if '--check' in sys.argv:
        assert target.read_text() == text, 'Regenerate caption-worker resources.yaml'
    else:
        target.write_text(text)


if __name__ == '__main__':
    main()
