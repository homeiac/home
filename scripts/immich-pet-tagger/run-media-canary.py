#!/usr/bin/env python3
"""Use existing Mac extra workers for a bounded no-write canary, then restore policy."""
import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys
import time
from distributed import request

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('directory',type=Path)
args=p.parse_args()
run='waffles-media-canary-20261127'
policy=request('/api/burst')['workers']['mac']
assert policy['slots']>0, 'Existing extra workers required'
backup=args.directory/'canary-burst-policy.json'
if backup.exists():
    assert json.loads(backup.read_text())==policy, 'Resolve previous policy restore before rerunning'
else:
    backup.write_text(json.dumps(policy,indent=2)+'\n')
print('START: routing existing Mac extras to no-write media canary; baseline unchanged',flush=True)
try:
    request('/admin/burst',{'worker':'mac',**policy,'mode':'benchmark','note':'Bounded media recovery canary; baseline preserved'})
    deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        rows=[r for r in request('/admin/status')['runs'] if r['id']==run]
        counts=Counter()
        for r in rows:counts[r['status']]+=r['jobs']
        print(json.dumps(dict(counts)),flush=True)
        if counts['complete']==34:
            subprocess.run([sys.executable,str(Path(__file__).with_name('recover-media.py')),'evaluate',str(args.directory)],check=True)
            break
        if counts['failed']:raise RuntimeError('Canary has failed jobs; inspect before recovery')
        time.sleep(5)
    else:raise TimeoutError('Canary exceeded 180 seconds')
finally:
    request('/admin/burst',{'worker':'mac',**policy,'note':'Restore existing policy after media canary'})
    print('RESTORED: original Mac extra-worker policy',flush=True)
