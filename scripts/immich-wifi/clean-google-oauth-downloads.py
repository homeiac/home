#!/usr/bin/env python3
"""Remove only matching OAuth downloads after verifying SOPS recovery."""
import json
import os
from pathlib import Path
import subprocess
import yaml

root = Path(__file__).resolve().parents[2]
os.environ.setdefault('SOPS_AGE_KEY_FILE', str(Path.home()/'.config/sops/age/keys.txt'))
secret = json.loads(subprocess.run(['sops', '--decrypt', '--output-type', 'json', str(root/'gitops/clusters/homelab/apps/photo-enrichment/immich-pilot/google-oauth.sops.yaml')], capture_output=True, text=True, check=True).stdout)
oauth = yaml.safe_load(secret['stringData']['values.yaml'])['immich']['configuration']['oauth']
removed = 0
for path in (Path.home()/'Downloads').glob('client_secret_*.json'):
    if path.is_symlink():
        continue
    try:
        client = json.loads(path.read_text()).get('web', {})
    except (ValueError, OSError):
        continue
    if client.get('client_id') == oauth['clientId'] and client.get('client_secret') == oauth['clientSecret']:
        path.unlink()
        removed += 1
print(f'Removed {removed} matching plaintext downloads after SOPS recovery verification')
