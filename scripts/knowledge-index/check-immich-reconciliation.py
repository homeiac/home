#!/usr/bin/env python3
"""Read-only reconciliation status and privilege checks; never prints credentials."""
import json
import os
from pathlib import Path
import subprocess

BASE=['kubectl','--kubeconfig',os.environ.get('KUBECONFIG',str(Path.home()/'kubeconfig'))]
def query(namespace, pod, database, user, sql):
    result=subprocess.run(BASE+['-n',namespace,'exec',pod,'--','psql','-XAt','-v','ON_ERROR_STOP=1','-U',user,'-d',database,'-c',sql],text=True,capture_output=True,check=True)
    return [json.loads(x) for x in result.stdout.splitlines() if x]

for label, sql in [
 ('queue',"SELECT jsonb_build_object('state',state,'reason',reason,'count',count(*)) FROM immich_sync.jobs GROUP BY state,reason ORDER BY count(*) DESC"),
 ('checkpoint',"SELECT value FROM immich_sync.state WHERE key='checkpoint'"),
 ('role',"SELECT jsonb_build_object('source_select',has_table_privilege('immich_reconciler','catalog.gphotos_media','SELECT'),'source_write',has_table_privilege('immich_reconciler','catalog.gphotos_media','INSERT,UPDATE,DELETE'),'queue_write',has_table_privilege('immich_reconciler','immich_sync.jobs','INSERT,UPDATE,DELETE'))"),
 ('progress',"SELECT jsonb_build_object('preserved',count(*) FILTER(WHERE state='applied'),'pending',count(*) FILTER(WHERE state='pending'),'last_applied',max(applied_at)) FROM immich_sync.jobs")]:
    print(json.dumps({label:query('database','postgres-postgresql-0','photo_enrichment','postgres',sql)}))
print(json.dumps({'immich_metadata':query('immich-pilot','deployment/immich-postgres','immich','immich',"SELECT jsonb_build_object('key',key,'count',count(*)) FROM asset_metadata WHERE key LIKE 'home.knowledge-index.%' GROUP BY key")}))
result=subprocess.run(BASE+['-n','immich-pilot','logs','deployment/immich-sync','--tail=5'],text=True,capture_output=True,check=True)
print(result.stdout,end='')
