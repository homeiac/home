#!/usr/bin/env python3
"""Create one scoped PostgreSQL password and queue credentials directly in SOPS."""
from pathlib import Path
import secrets
import subprocess
import yaml

root = Path(__file__).resolve().parents[2]
target = root / 'gitops/clusters/homelab/apps/photo-enrichment/immich-pet-tagger/queue-credentials.sops.yaml'
if target.exists():
    raise SystemExit('Queue credentials already exist; refusing accidental rotation')
password = secrets.token_hex(32)
documents = [dict(apiVersion='v1', kind='Secret', metadata=dict(name='waffles-queue', namespace=namespace),
                  type='Opaque', stringData=values) for namespace, values in [
    ('database', {'password': password}),
    ('immich-pilot', {'password': password, 'worker-token': secrets.token_hex(32), 'admin-token': secrets.token_hex(32)})]]
result = subprocess.run(['sops', '--encrypt', '--input-type', 'yaml', '--output-type', 'yaml',
                         '--filename-override', str(target), '/dev/stdin'],
                        input=yaml.safe_dump_all(documents, sort_keys=False), text=True, capture_output=True)
if result.returncode:
    raise SystemExit('SOPS encryption failed; plaintext suppressed')
target.write_text(result.stdout)
