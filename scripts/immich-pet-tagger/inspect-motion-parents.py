#!/usr/bin/env python3
"""Find linked still images for failed derived motion clips using read-only Immich SQL."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import uuid
from distributed import KUBE
p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);a=p.parse_args();os.umask(0o077)
assets=json.loads((a.directory/'assets.json').read_text())
ids=','.join("'"+str(uuid.UUID(r['id']))+"'" for r in assets if r['type']=='VIDEO')
sql='BEGIN READ ONLY; SET LOCAL statement_timeout=\'20s\'; SELECT jsonb_build_object(\'id\',id,\'video_id\',"livePhotoVideoId",\'path\',"originalPath",\'name\',"originalFileName") FROM asset WHERE "livePhotoVideoId" IN ('+ids+'); COMMIT;'
r=subprocess.run(KUBE+['-n','immich-pilot','exec','-i','deployment/immich-postgres','--','psql','-XAtq','-v','ON_ERROR_STOP=1','-U','immich','-d','immich'],input=sql,text=True,capture_output=True,check=True)
rows=[json.loads(line) for line in r.stdout.splitlines() if line.startswith('{')]
(a.directory/'motion-parents.json').write_text(json.dumps(rows,indent=2)+'\n')
for i,asset in enumerate(assets):
    if asset['type']=='VIDEO':print(json.dumps({'index':i,'linked_stills':sum(r['video_id']==asset['id'] for r in rows)}))
