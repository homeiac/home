"""Freeze the private asset UUID cohort once, using read-only database queries."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('ledger', type=Path)
args = parser.parse_args()
kub = ['kubectl', '--kubeconfig', str(Path.home() / 'kubeconfig'), '-n', 'immich-pilot', 'exec', '-i']

def run(command, sql):
    return subprocess.check_output(kub + command, input=sql, text=True, timeout=180)

os.umask(0o077)
ledger=sqlite3.connect(args.ledger)
ledger.execute('create table if not exists cohort(id text primary key, cohort text, media_type text, path text, size integer, visibility text, file_updated text, has_packet integer)')
if ledger.execute('select count(*) from cohort').fetchone()[0]:
    raise SystemExit('Existing snapshot retained')
q=json.loads(run(['deploy/waffles-queue','--','node','--input-type=module','-'], """
import {createRequire} from 'node:module';
const {Client}=createRequire('/usr/src/app/server/package.json')('pg');
const db=new Client(); await db.connect(); await db.query('BEGIN READ ONLY');
const r=await db.query("select asset_id,status from waffles.jobs where run_id='historical-waffles' and (status='complete' or (status='failed' and last_error='thumbnail_http_404'))");
await db.end(); console.log(JSON.stringify(r.rows));"""))
status={x['asset_id']:x['status'] for x in q}
args=['deploy/immich-postgres','--','psql','-XqAt','-v','ON_ERROR_STOP=1','-U','immich','-d','immich']
sql="""BEGIN READ ONLY;
select json_build_array(a.id,a.type,a."originalPath",e."fileSizeInByte",a.visibility,a."fileModifiedAt",m.value IS NOT NULL,
 nullif(btrim(e.description),'') IS NULL AND nullif(btrim(m.value->>'summary'),'') IS NULL)
from asset a left join asset_exif e on e."assetId"=a.id left join asset_metadata m on m."assetId"=a.id and m.key='home.knowledge-index.v1'
where a."deletedAt" is null and not a."isOffline"; ROLLBACK;"""
for l in run(args,sql).splitlines():
    uid,kind,path,size,vis,updated,has_packet,blank=json.loads(l)
    state=status.get(uid)
    if state=='failed' or state=='complete' and blank:
        ledger.execute('insert into cohort values(?,?,?,?,?,?,?,?)',(uid,'thumbnail' if state=='failed' else 'caption',kind,path,size,vis,updated,has_packet))
ledger.commit()
for r in ledger.execute("select cohort,media_type,visibility,has_packet,count(*),sum(size is null) from cohort group by 1,2,3,4"): print(r)
