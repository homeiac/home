#!/usr/bin/env python3
"""Validate GitOps rendering, the scan gate and encrypted secret recovery locally."""
import os
from pathlib import Path
import subprocess
import sys
import yaml

root = Path(__file__).resolve().parents[2]
directory = root/'gitops/clusters/homelab/apps/photo-enrichment/immich-pet-tagger'
subprocess.run([sys.executable, str(Path(__file__).with_name('test-startup.py'))], check=True)
rendered = subprocess.check_output(['kubectl', 'kustomize', str(directory)], text=True)
documents = list(yaml.safe_load_all(rendered))
deployment = next(d for d in documents if d['kind'] == 'Deployment')
container = deployment['spec']['template']['spec']['containers'][0]
assert '@sha256:' in container['image'] and ':latest' not in container['image']
assert deployment['spec']['template']['spec']['automountServiceAccountToken'] is False
assert container['securityContext']['readOnlyRootFilesystem'] is True
configmap = next(d for d in documents if d['kind'] == 'ConfigMap')
assert configmap['data']['startup.py'] == Path(__file__).with_name('startup.py').read_text()
secret_file = directory/'credentials.sops.yaml'
encrypted = yaml.safe_load(secret_file.read_text())
assert encrypted['stringData']['api-key'].startswith('ENC[AES256_GCM,')
environment = dict(os.environ)
environment.setdefault('SOPS_AGE_KEY_FILE', str(Path.home()/'.config/sops/age/keys.txt'))
decoded = subprocess.run(['sops', '-d', str(secret_file)], capture_output=True,
                         text=True, env=environment)
if decoded.returncode:
    raise SystemExit('SOPS recovery failed; plaintext and stderr suppressed')
key = yaml.safe_load(decoded.stdout)['stringData']['api-key']
assert len(key) >= 24 and key not in rendered
diff = subprocess.check_output(['git', '-C', str(root), 'diff', '--cached'], text=True)
assert key not in diff
subprocess.run(['kubectl', 'kustomize', str(directory.parent)], check=True,
               stdout=subprocess.DEVNULL)
subprocess.run(['git', '-C', str(root), 'diff', '--check'], check=True)
print('Validated full stack, pinned image, startup gate, and SOPS secret recovery')
