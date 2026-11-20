#!/usr/bin/env python3
"""Encrypt dedicated sync credentials for Flux; never print plaintext values."""
import argparse
from pathlib import Path
import secrets
import subprocess
import yaml

ROOT=Path(__file__).resolve().parents[2]
DEST=ROOT/'gitops/clusters/homelab/apps/photo-enrichment/immich-sync'

def encrypted(target,documents):
    result=subprocess.run(['sops','--encrypt','--input-type','yaml','--output-type','yaml','--filename-override',str(target),'/dev/stdin'],input=yaml.safe_dump_all(documents,sort_keys=False),text=True,capture_output=True)
    if result.returncode:raise RuntimeError('SOPS encryption failed; use the repository age recovery runbook')
    target.write_text(result.stdout)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-key-file',type=Path,required=True)
    args=parser.parse_args()
    DEST.mkdir(parents=True,exist_ok=True)
    target=DEST/'credentials.sops.yaml'
    if target.exists():raise SystemExit('Credential manifest exists; refusing accidental rotation')
    key=args.api_key_file.read_text().strip()
    if len(key)<24:raise SystemExit('Invalid API key file')
    password=secrets.token_urlsafe(36)
    def secret(namespace,name,data):
        return dict(apiVersion='v1',kind='Secret',metadata=dict(namespace=namespace,name=name),type='Opaque',stringData=data)
    encrypted(target,[secret('immich-pilot','immich-sync',{'api-key':key,'pg-password':password}),secret('database','immich-sync-bootstrap',{'password':password})])
    print('Encrypted API and database credentials written for Flux; no plaintext output.')
