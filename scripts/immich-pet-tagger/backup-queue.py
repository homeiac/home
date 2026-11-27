#!/usr/bin/env python3
"""Back up the private Waffles schema and verify its custom-format archive index."""
import argparse
from datetime import datetime,timezone
import os
from pathlib import Path
import subprocess
from distributed import KUBE,secret

parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory',type=Path)
parser.add_argument('--verify',type=Path,help='Verify an existing private archive without creating another backup')
args=parser.parse_args()
os.umask(0o077);args.directory.mkdir(parents=True,exist_ok=True)
destination=args.verify or args.directory/('waffles-before-schema-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.dump')
command=['sh','-c','IFS= read -r PGPASSWORD; export PGPASSWORD; exec pg_dump -h postgres-postgresql.database.svc.cluster.local -U waffles_worker -d photo_enrichment -n waffles -Fc -w']
if not args.verify:
    with destination.open('xb') as stream:
        subprocess.run(KUBE+['-n','database','exec','-i','postgres-postgresql-0','--']+command,input=(secret('password')+'\n').encode(),stdout=stream,check=True,timeout=300)
# Local pg_restore avoids a remote stdin stream and can read the entire archive.
index=subprocess.check_output(['pg_restore','--list',str(destination)],text=True,timeout=30)
assert 'TABLE DATA waffles jobs' in index and 'TABLE DATA waffles settings' in index
subprocess.run(['pg_restore','--file=/dev/null',str(destination)],check=True,timeout=120)
print('Verified private queue backup:',destination,'bytes=',destination.stat().st_size)
