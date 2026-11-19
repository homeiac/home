#!/usr/bin/env python3
"""Read retry categories and EXIF text validity without exposing photo paths."""
import os
import shlex
import subprocess

REMOTE = r'''
import os,sys,json
from pathlib import Path
root=Path('/opt/photo-enrichment/current')
os.environ.update(PGSERVICEFILE='/etc/photo-enrichment/pg_service.conf',PGPASSFILE='/etc/photo-enrichment/pgpass')
sys.path.insert(0,str(root))
from photo_enrichment.postgres import connect
from photo_enrichment.metadata import read_metadata,contained
pid=__import__('subprocess').check_output(['systemctl','show','knowledge-index-enrich','-p','MainPID','--value'],text=True).strip()
argv=Path('/proc',pid,'cmdline').read_bytes().decode().split('\0')
library=Path(argv[argv.index('--library')+1])
with connect() as c:
 rows=c.execute("SELECT j.path,m.sidecar_path,j.timezone FROM photo_jobs j JOIN catalog.gphotos_media m USING(path) WHERE j.status='retry' AND j.last_error='DataError' LIMIT 10").fetchall()
 invalid={}
 errors={}
 for path,sidecar,timezone in rows:
  try:
   c.execute('SELECT * FROM enriched_media WHERE path=%s',[path]).fetchone()
  except Exception as exc:
   categories=[word for word in ('NUL','timestamp','year','numeric','encoding','infinite','overflow','range') if word.lower() in str(exc).lower()]
   key=type(exc).__name__+':'+','.join(categories)
   errors[key]=errors.get(key,0)+1
  data=read_metadata(contained(library,path),contained(library,sidecar) if sidecar else None,timezone)
  for key,value in data.items():
   if isinstance(value,str) and chr(0) in value:invalid[key]=invalid.get(key,0)+1
 print(json.dumps({'sampled_retries':len(rows),'fields_with_nul':invalid,'catalog_decode_errors':errors}))
'''

if __name__=='__main__':
    subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10',os.environ['CB_HOST'],
        '/opt/photo-enrichment/current/venv/bin/python -c '+shlex.quote(REMOTE)],check=True)
