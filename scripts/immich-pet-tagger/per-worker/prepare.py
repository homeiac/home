#!/usr/bin/env python3
"""Freeze approved holdout bytes and classifier for identical CPU/Metal trials."""
import argparse,json,hashlib,shutil,os
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);a=p.parse_args();os.umask(0o077)
a.directory.mkdir(parents=True,exist_ok=False);root=Path('/private/tmp/waffles-pet-tagger-private');source=root/'reject-review-20261127'
truth=json.loads((root/'owner-confirmed-holdout.json').read_text());rows=[]
for label in ['positive','negative']:
 for asset in truth[label]:
  index=len(rows);filename=f'images/{index:03}.jpg';target=a.directory/filename;target.parent.mkdir(exist_ok=True);shutil.copy2(source/'targets'/(asset+'.jpg'),target)
  rows.append({'index':index,'file':filename,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'expected':label})
(a.directory/'manifest.json').write_text(json.dumps(rows,indent=2)+'\n');shutil.copy2(root/'distributed/classifier.json',a.directory/'classifier.json')
shutil.copy2(Path(__file__).with_name('worker.py'),a.directory/'worker.py')
print(json.dumps({'photos':len(rows),'manifest_sha256':hashlib.sha256((a.directory/'manifest.json').read_bytes()).hexdigest()}))
