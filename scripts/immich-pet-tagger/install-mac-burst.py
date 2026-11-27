#!/usr/bin/env python3
"""Install a separate extra-worker LaunchAgent without stopping the Mac baseline."""
import argparse
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import time

here=Path(__file__).resolve().parent
root=Path.home()/'Library/Application Support/immich-pet-tagger'
label='com.panderosystems.waffles-burst-workers'
plist=Path.home()/'Library/LaunchAgents'/(label+'.plist')
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['start','stop','status'])
args=parser.parse_args();identity=f'gui/{os.getuid()}/{label}'
if args.action=='status':subprocess.run(['launchctl','print',identity],check=True);raise SystemExit
if args.action=='stop':subprocess.run(['launchctl','bootout',identity],check=True);raise SystemExit
os.umask(0o077)
destination=root/'burst';destination.mkdir(parents=True,exist_ok=True)
for name in ('burst-worker.py','burst-supervisor.py','burst_guard.py','mac_observation.py'):
    if (destination/name).exists():shutil.copy2(destination/name,destination/(name+'.previous'))
    shutil.copy2(here/name,destination/name)
assert (root/'venv/bin/python').exists() and (root/'worker-token').exists()
config={'Label':label,'ProgramArguments':['/usr/bin/caffeinate','-s',str(root/'venv/bin/python'),'-B',str(destination/'burst-supervisor.py')],
        'RunAtLoad':True,'KeepAlive':True,'ThrottleInterval':30,'WorkingDirectory':str(root/'data'),
        'StandardOutPath':str(destination/'worker.log'),'StandardErrorPath':str(destination/'worker.log'),
        'EnvironmentVariables':{'QUEUE_URL':'https://pets-queue.app.home.panderosystems.com','WORKER_NAME':'mac',
           'WORKER_TOKEN_FILE':str(root/'worker-token'),'UPSTREAM_APP':(root/'upstream-app.txt').read_text(),
           'DATA_DIR':str(root/'data'),'BURST_READY_DIR':str(destination/'ready'),'MODEL_WORKERS':'1','SCAN_WORKERS':'1',
           'OMP_NUM_THREADS':'2','MKL_NUM_THREADS':'2','OPENBLAS_NUM_THREADS':'2'}}
if plist.exists():
    shutil.copy2(plist,destination/'previous.plist')
    subprocess.run(['launchctl','bootout',identity],capture_output=True)
    deadline=time.monotonic()+30
    while subprocess.run(['launchctl','print',identity],capture_output=True).returncode==0:
        if time.monotonic()>deadline:raise RuntimeError('Previous burst supervisor still stopping')
        time.sleep(.25)
plist.write_bytes(plistlib.dumps(config))
subprocess.run(['launchctl','bootstrap',f'gui/{os.getuid()}',str(plist)],check=True)
print('Started separate burst supervisor; baseline LaunchAgent remains running')
