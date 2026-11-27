#!/usr/bin/env python3
"""Record or verify that adding burst services does not restart baseline workers."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
from distributed import KUBE,request

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--save',type=Path);parser.add_argument('--compare',type=Path)
args=parser.parse_args()
pods=json.loads(subprocess.check_output(KUBE+['-n','immich-pilot','get','pods','-l','app in (waffles-worker-pve,waffles-worker-still-fawn)','-o','json'],text=True))
identity={p['metadata']['labels']['app']:{'uid':p['metadata']['uid'],'restarts':sum(c['restartCount'] for c in p['status'].get('containerStatuses',[]))} for p in pods['items']}
agent=subprocess.check_output(['launchctl','print',f'gui/{os.getuid()}/com.panderosystems.waffles-worker'],text=True)
identity['mac']={'launch_pid':int(re.search(r'\bpid = (\d+)',agent)[1])}
if args.save:
    if args.save.exists():raise RuntimeError('Do not overwrite the pre-change baseline identity record')
    args.save.write_text(json.dumps(identity,indent=2)+'\n')
if args.compare:assert identity==json.loads(args.compare.read_text()),'A baseline process or pod restarted'
status=request('/admin/status');counts={}
for row in status['runs']:
    if row['id']=='historical-waffles' and row['status']=='complete':counts[row['worker']]=row['jobs']
print(json.dumps({'baseline_identity':identity,'historical_processed_by_backend':counts,'baseline_unchanged':bool(args.compare)},indent=2))
