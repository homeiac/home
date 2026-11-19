#!/usr/bin/env python3
"""Provision and migrate the existing photo worker; credentials never enter Git (#217)."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shlex
import subprocess


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('inspect','prepare','cutover','status'))
    args=parser.parse_args()
    here=Path(__file__).resolve().parent
    host=os.environ['CB_HOST']
    env=dict(os.environ,KUBECONFIG=os.environ.get('KUBECONFIG',str(Path.home()/'kubeconfig')))
    def pg(statement):
        result=subprocess.run(['kubectl','-n','database','exec','-i','postgres-postgresql-0','--',
            'psql','-X','-U','postgres','-d','postgres','-At','-v','ON_ERROR_STOP=1'],
            input=statement,text=True,capture_output=True,env=env)
        if result.returncode: raise RuntimeError('PostgreSQL provisioning failed; output suppressed to protect credentials')
        return result.stdout.strip()
    payload={'mode':args.mode}
    if args.mode=='prepare':
        exists=pg("SELECT count(*) FROM pg_roles WHERE rolname='photo_enrichment';")=='1'
        if not exists:
            password=secrets.token_hex(32)
            pg("SET log_statement='none'; CREATE ROLE photo_enrichment LOGIN PASSWORD '"+password+"';")
            pg('CREATE DATABASE photo_enrichment OWNER photo_enrichment;')
            payload['pgpass']=password
        elif pg("SELECT count(*) FROM pg_database WHERE datname='photo_enrichment';")!='1':
            raise RuntimeError('Existing role has no matching database; inspect before continuing')
    if args.mode in ('prepare','cutover'):
        files={'photo-enrich.py':(here/'photo-enrich.py').read_text()}
        for path in sorted((here/'photo_enrichment').rglob('*')):
            if path.is_file() and path.suffix in ('.py','.html','.css','.js','.txt','.md'):
                files[str(path.relative_to(here))]=path.read_text()
        payload['files']=files
        payload['release']=hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()[:16]
    remote=(here/'host/rollout-photo-postgres.py').read_text()
    subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10',host,
        'python3 -c '+shlex.quote(remote)],input=json.dumps(payload),text=True,check=True)


if __name__=='__main__':main()
