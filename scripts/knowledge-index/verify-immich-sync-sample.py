#!/usr/bin/env python3
"""Compare API-preserved records to checkpoints and native fields to a private audit."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import urllib.request

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--audit',type=Path,required=True)
p.add_argument('--limit',type=int,default=5)
a=p.parse_args()
key=Path('/private/tmp/immich-sync-api-key').read_text().strip()
def api(route):
    request=urllib.request.Request('https://immich.app.home.panderosystems.com/api'+route,headers={'x-api-key':key})
    with urllib.request.urlopen(request,timeout=45) as response:return json.load(response)
def timestamp(value):
    if not value:return None
    value=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
    return value.replace(tzinfo=value.tzinfo or dt.timezone.utc).timestamp()
base=['kubectl','--kubeconfig',os.environ.get('KUBECONFIG',str(Path.home()/'kubeconfig'))]
sql="SELECT jsonb_build_object('id',asset_id,'applied',applied) FROM immich_sync.jobs WHERE state='applied' ORDER BY applied_at LIMIT "+str(max(1,min(a.limit,100)))
result=subprocess.run(base+['-n','database','exec','postgres-postgresql-0','--','psql','-XAt','-v','ON_ERROR_STOP=1','-U','postgres','-d','photo_enrichment','-c',sql],text=True,capture_output=True,check=True)
rows=[json.loads(x) for x in result.stdout.splitlines()]
if not rows:raise RuntimeError('No applied records to verify')
baselines={x['id']:x for x in map(json.loads,(a.audit/'target.jsonl').read_text().splitlines())}
for row in rows:
    metadata=api('/assets/'+row['id']+'/metadata')
    saved=next(x['value'] for x in metadata if x['key']=='home.knowledge-index.v1')
    assert saved==row['applied'],'Checkpoint and API metadata differ'
    exif=api('/assets/'+row['id']).get('exifInfo') or {}
    old=baselines[row['id']]
    for k in ['description','latitude','longitude']:
        assert exif.get(k)==old.get(k),'Native '+k+' changed since audit'
    assert timestamp(exif.get('dateTimeOriginal'))==timestamp(old.get('taken_at')),'Native date changed since audit'
    assert len(saved['contentSha256'])==64,'Missing content verification'
print(json.dumps({'sampled':len(rows),'custom_metadata_readback':'passed','native_description_gps_date':'unchanged','content_hash':'present'}))
