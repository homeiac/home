#!/usr/bin/env python3
"""Render an isolated Ollama Bonsai vision canary for Flux."""
import argparse
from pathlib import Path
import yaml

root = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--gpu', action='store_true')
args = parser.parse_args()
name = 'ollama-bonsai-vision-gpu-v1' if args.gpu else 'ollama-bonsai-vision-canary-v1'
metadata = {'name': name, 'namespace': 'ollama' if args.gpu else 'immich-pilot'}
script = Path(__file__).with_name('check-ollama-bonsai.mjs').read_text()
image = 'ollama/ollama:0.40.17@sha256:ccc42bcd3d5fcf7ab0d532b300382154e1a4da56fc666bdb313b78ebdd912754'
node_image = 'ghcr.io/immich-app/immich-server:v3.4.2@sha256:fc880c1bf665b4aab1e74c15e56ab871225989cd546536e6b77e771869af06bd'
labels = {'app': name}
env = {'OLLAMA_HOST': '127.0.0.1:11434', 'OLLAMA_MODELS': '/store', 'OLLAMA_NO_CLOUD': 'true',
       'OLLAMA_NUM_PARALLEL': '1', 'OLLAMA_MAX_LOADED_MODELS': '1', 'CUDA_VISIBLE_DEVICES': '-1'}
if args.gpu:
    env.update(CUDA_VISIBLE_DEVICES='0', OLLAMA_FLASH_ATTENTION='true',
               OLLAMA_GPU_OVERHEAD='1073741824', OLLAMA_NOPRUNE='true')
security = {'allowPrivilegeEscalation': False, 'capabilities': {'drop': ['ALL']}}
store = {'name': 'store', 'mountPath': '/store'}
server = {'name': 'ollama', 'image': image, 'args': ['serve'], 'restartPolicy': 'Always',
          'env': [{'name': key, 'value': value} for key, value in env.items()],
          'startupProbe': {'exec': {'command': ['ollama', 'list']}, 'periodSeconds': 5, 'failureThreshold': 24},
          'resources': {'requests': {'cpu': '500m', 'memory': '2Gi'}, 'limits': {'cpu': '2', 'memory': '10Gi'}},
          'securityContext': security, 'volumeMounts': [store]}
test = {'name': 'canary', 'image': node_image, 'command': ['node', '/scripts/check.mjs'],
        'resources': {'requests': {'cpu': '100m', 'memory': '128Mi'}, 'limits': {'cpu': '1', 'memory': '512Mi'}},
        'securityContext': security, 'volumeMounts': [store, {'name': 'source', 'mountPath': '/source', 'readOnly': True},
                                                     {'name': 'script', 'mountPath': '/scripts', 'readOnly': True}]}
spec = {'restartPolicy': 'Never', 'automountServiceAccountToken': False,
        'nodeSelector': {'kubernetes.io/hostname': 'k3s-vm-pumped-piglet-gpu'},
        'securityContext': {'seccompProfile': {'type': 'RuntimeDefault'}},
        'initContainers': [server], 'containers': [test],
        'volumes': [{'name': 'store', 'emptyDir': {'sizeLimit': '8Gi'}},
                    {'name': 'source', 'hostPath': {'path': '/var/lib/photo-models/bonsai-27b', 'type': 'Directory'}},
                    {'name': 'script', 'configMap': {'name': name}}]}
if args.gpu:
    spec['runtimeClassName'] = 'nvidia'
    spec['volumes'][0] = {'name': 'store', 'persistentVolumeClaim': {'claimName': 'ollama-models'}}
    server['resources']['requests']['nvidia.com/gpu'] = '1'
    server['resources']['limits']['nvidia.com/gpu'] = '1'
    test['env'] = [{'name': 'REQUIRE_GPU', 'value': 'true'}]
resources = [
    {'apiVersion': 'v1', 'kind': 'ConfigMap', 'metadata': metadata, 'data': {'check.mjs': script}},
    {'apiVersion': 'networking.k8s.io/v1', 'kind': 'NetworkPolicy', 'metadata': metadata,
     'spec': {'podSelector': {'matchLabels': labels}, 'policyTypes': ['Ingress', 'Egress']}},
    {'apiVersion': 'batch/v1', 'kind': 'Job', 'metadata': metadata,
     'spec': {'backoffLimit': 0, 'activeDeadlineSeconds': 1500,
              'template': {'metadata': {'labels': labels}, 'spec': spec}}},
]
target = root / 'gitops/clusters/homelab/apps/photo-enrichment/ollama-bonsai-canary.yaml'
target.write_text(yaml.safe_dump_all(resources, sort_keys=False))
