#!/usr/bin/env python3
"""Look for existing local versions/backups of only the six damaged filenames."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

items=[i for i in json.loads(Path('/var/tmp/caption-gaps-20261122.json').read_text()) if 'decode_error' in i]
names={Path(i['path']).name:i['job_id'] for i in items}
roots=[Path('/local-3TB-backup/gphotos/.versions'),Path('/mnt/ssk-cloud/cloud-backup'),
       Path('/mnt/ssk-cloud/.versions'),Path('/mnt/wd25-cloud/cloud-backup')]
found=[]
for root in roots:
    scanned=0
    if root.exists():
        for directory,dirs,files in os.walk(root):
            dirs[:]=[d for d in dirs if d not in ('.zfs','$RECYCLE.BIN','System Volume Information')]
            scanned+=len(files)
            for name in set(files)&names.keys():
                p=Path(directory)/name
                with p.open('rb') as stream:
                    digest=hashlib.file_digest(stream,'sha256').hexdigest()
                probe=subprocess.run(['ffprobe','-v','error','-show_entries','stream=codec_type,width,height',
                    '-of','json',str(p)],capture_output=True,text=True,timeout=60)
                info={'job_id':names[name],'root':str(root),'bytes':p.stat().st_size,'sha256':digest,
                      'probe':json.loads(probe.stdout or '{}')}
                print(json.dumps(info),flush=True)
                found.append({'path':str(p),**info})
    print('Scanned',str(root),'files',scanned,flush=True)
for root in (Path('/mnt/ssk-cloud'),Path('/mnt/wd25-cloud')):
    print('Top-level recovery directories',str(root),[p.name for p in root.iterdir() if p.is_dir()][:50])
target=Path('/var/tmp/caption-gap-copies.json')
target.write_text(json.dumps(found,indent=2));target.chmod(0o600)
