#!/usr/bin/env python3
"""Encrypt a dedicated private API-key file for Flux without printing plaintext."""
import argparse
from pathlib import Path
import subprocess
import yaml

root = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('key_file', type=Path)
args = parser.parse_args()
target = root/'gitops/clusters/homelab/apps/photo-enrichment/immich-pet-tagger/credentials.sops.yaml'
if target.exists():
    raise SystemExit('Secret already exists; refusing accidental rotation')
key = args.key_file.read_text().strip()
if len(key) < 24 or '\n' in key:
    raise SystemExit('Invalid key file')
document = dict(apiVersion='v1', kind='Secret', metadata=dict(
    name='immich-pet-tagger', namespace='immich-pilot'), type='Opaque',
    stringData={'api-key': key})
result = subprocess.run(['sops', '--encrypt', '--input-type', 'yaml', '--output-type',
    'yaml', '--filename-override', str(target), '/dev/stdin'],
    input=yaml.safe_dump(document, sort_keys=False), text=True, capture_output=True)
if result.returncode:
    raise SystemExit('SOPS encryption failed; plaintext output suppressed')
target.write_text(result.stdout)
kustomization = target.with_name('kustomization.yaml')
configuration = yaml.safe_load(kustomization.read_text())
if target.name not in configuration['resources']:
    configuration['resources'].append(target.name)
    kustomization.write_text(yaml.safe_dump(configuration, sort_keys=False))
print('Wrote SOPS encrypted pet-tagger key')
