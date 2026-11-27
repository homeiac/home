#!/usr/bin/env python3
"""Render the pinned chart privately and verify the OAuth security boundaries."""
import base64
import json
import os
from pathlib import Path
import subprocess
import yaml

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT/'gitops/clusters/homelab/apps/photo-enrichment/immich-pilot'
os.environ.setdefault('SOPS_AGE_KEY_FILE', str(Path.home()/'.config/sops/age/keys.txt'))
release = list(yaml.safe_load_all((BUNDLE/'release.yaml').read_text()))[1]
secret = json.loads(subprocess.run(['sops', '--decrypt', '--output-type', 'json', str(BUNDLE/'google-oauth.sops.yaml')], capture_output=True, text=True, check=True).stdout)
values = yaml.safe_load(secret['stringData']['values.yaml'])

def merge(target, override):
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            merge(target[key], value)
        else:
            target[key] = value

merge(values, release['spec']['values'])
rendered = subprocess.run(['helm', 'template', 'immich', 'immich', '--repo', 'https://immich-app.github.io/immich-charts', '--version', '0.12.0', '--namespace', 'immich-pilot', '-f', '-'], input=yaml.safe_dump(values), capture_output=True, text=True)
if rendered.returncode:
    raise SystemExit('Helm rendering failed; output suppressed to protect credentials')
docs = [d for d in yaml.safe_load_all(rendered.stdout) if d]
configs = [d for d in docs if 'immich-config.yaml' in d.get('data', {}) or 'immich-config.yaml' in d.get('stringData', {})]
assert len(configs) == 1 and configs[0]['kind'] == 'Secret', 'Configuration must render into one Secret'
config = configs[0]
encoded = config.get('data', {}).get('immich-config.yaml')
body = base64.b64decode(encoded).decode() if encoded else config['stringData']['immich-config.yaml']
settings = yaml.safe_load(body)
assert settings['oauth']['enabled'] and not settings['oauth']['autoRegister']
assert not settings['oauth']['autoLaunch'] and settings['passwordLogin']['enabled']
assert settings['oauth']['scope'] == 'openid email profile'
assert settings['oauth']['mobileOverrideEnabled']
assert settings['oauth']['mobileRedirectUri'].endswith('/api/oauth/mobile-redirect')
assert settings['storageTemplate'] == release['spec']['values']['immich']['configuration']['storageTemplate']
assert settings['ffmpeg'] == release['spec']['values']['immich']['configuration']['ffmpeg']
for doc in docs:
    if doc['kind'] == 'ConfigMap':
        assert settings['oauth']['clientSecret'] not in yaml.safe_dump(doc)
server = next(d for d in docs if d['kind'] == 'Deployment' and d['metadata']['name'] == 'immich-server')
assert any(v.get('secret', {}).get('secretName') == config['metadata']['name'] for v in server['spec']['template']['spec']['volumes'])
print('Passed: Secret configuration mounted; registration closed; password fallback and existing storage/GPU settings preserved; web/mobile OAuth configured.')
