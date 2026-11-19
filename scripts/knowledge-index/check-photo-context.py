#!/usr/bin/env python3
"""Verify context jobs and service health without exposing private locations."""
import argparse
import json
import os
import shlex
import subprocess

REMOTE=r'''
import json,os,pathlib,subprocess,sys
args=json.load(sys.stdin)
for action in ('catalog','export'):
    if args.get(action):subprocess.run(['systemctl','start','--no-block','photo-enrichment-'+action+'.service'],check=True)
for name in ('gui','context','catalog','export'):
    print(name,subprocess.check_output(['systemctl','show','photo-enrichment-'+name+'.service','-p','ActiveState','-p','SubState','-p','ExecMainStatus','-p','NRestarts'],text=True).strip())
code=r"""
import json,os,sys
from photo_enrichment.postgres import connect
os.environ.update(PGSERVICEFILE='/etc/photo-enrichment/pg_service.conf',PGPASSFILE='/etc/photo-enrichment/pgpass',PHOTO_PG_SERVICE='photo_pipeline')
with connect() as c:
    if c.execute("SELECT to_regclass('public.photo_context')").fetchone()[0]:
        print('Context jobs',c.execute('SELECT status,count(*) FROM photo_context GROUP BY status').fetchall())
        print('Jobs with saved names',c.execute("SELECT count(*) FILTER(WHERE jsonb_array_length(input->'people')>0),count(*) FILTER(WHERE jsonb_array_length(input->'people')>0 AND status='done') FROM photo_context").fetchone())
        print('Next named photo',c.execute("SELECT regexp_replace(path,'^.*/','') FROM photo_context WHERE status='ready' AND jsonb_array_length(input->'people')>0 ORDER BY (input->>'capture_ts')::double precision DESC NULLS LAST LIMIT 1").fetchone())
        print('Place cache',c.execute('SELECT count(*) FROM photo_place_cache').fetchone()[0])
        print('Lookup budget',c.execute('SELECT requests,available_at FROM photo_place_budget').fetchall())
        if sys.argv[1]:
            row=c.execute("SELECT status,error_type,summary,context FROM photo_context WHERE regexp_replace(path,'^.*/','')=%s",[sys.argv[1]]).fetchone()
            if row:print('Example',json.dumps(dict(status=row[0],error_type=row[1],summary=row[2],candidates=[p['title'] for p in (row[3] or {}).get('candidates',[])])))
    print('Catalog freshness',c.execute("SELECT updated_at FROM pipeline_state WHERE key='catalog'").fetchone())
"""
subprocess.run(['/opt/photo-enrichment/gui/venv/bin/python','-c',code,args.get('photo','')],cwd='/opt/photo-enrichment/gui',check=True)
manifest=pathlib.Path('/local-3TB-backup/photo-enrichment/analytics/current.json')
if manifest.exists():
    snapshot=json.loads(manifest.read_text())
    print('Derived index rows',{key:value['rows'] for key,value in snapshot['tables'].items() if key in ('photo_search','photo_group_index')})
logs=subprocess.check_output(['journalctl','-u','photo-enrichment-context','-n','15','--no-pager','-o','cat'],text=True)
prom=pathlib.Path('/var/lib/prometheus/node-exporter/photo_context.prom')
if prom.exists():
    print('Context stages', '\n'.join(line for line in prom.read_text().splitlines() if line.startswith(('photo_context_worker_stage','photo_context_stage_started','photo_context_running'))))
for line in logs.splitlines():
    if line.startswith('{') or line.startswith(('RuntimeError:','psycopg.errors.','ModuleNotFoundError:')):print(line)
'''


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--photo',default='',help='Optional filename whose caption/candidate names may be displayed')
    parser.add_argument('--catalog',action='store_true',help='Run the catalog refresh now')
    parser.add_argument('--export',action='store_true',help='Publish an analytical snapshot now')
    args=parser.parse_args()
    subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10',os.environ['CB_HOST'],
        'python3 -c '+shlex.quote(REMOTE)],input=json.dumps(vars(args)),text=True,check=True)
