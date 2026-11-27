#!/usr/bin/env python3
"""Read nettop counters for the already-running Mac tagger processes, no test jobs."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess
import psutil

p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);args=p.parse_args()
os.umask(0o077);args.directory.mkdir(parents=True,exist_ok=True)
root=Path.home()/'Library/Application Support/immich-pet-tagger'
workers=[]
for process in psutil.process_iter(['pid','cmdline']):
    argv=process.info['cmdline'] or []
    if str(root/'worker.py') in argv:workers.insert(0,process.pid)
    elif str(root/'burst/burst-worker.py') in argv:workers.append(process.pid)
workers=workers[:3]
if not workers:raise RuntimeError('No existing Mac workers found')
path=args.directory/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-nettop.csv')
cmd=['/usr/bin/nettop','-P','-n','-x','-L','5','-s','5']
for pid in workers:cmd+=['-p',str(pid)]
with path.open('w') as stream:result=subprocess.run(cmd,stdout=stream,stderr=subprocess.PIPE,text=True,timeout=35)
print(json.dumps({'pids':workers,'path':str(path),'returncode':result.returncode,'error':result.stderr.strip()}))
