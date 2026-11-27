#!/usr/bin/env python3
"""Gracefully stop only this Waffles experiment, allowing its restoration finally block."""
import os
from pathlib import Path
import shlex
import signal
import subprocess

target=['scripts/immich-pet-tagger/experiment.py','/private/tmp/waffles-pet-tagger-private']
found=[]
for line in subprocess.check_output(['ps','-axo','pid=,args='],text=True).splitlines():
    pid,command=line.strip().split(None,1)
    try:args=shlex.split(command)
    except ValueError:continue
    if len(args)==3 and args[1:]==target and 'python' in Path(args[0]).name.lower():
        os.kill(int(pid),signal.SIGTERM);found.append(int(pid))
print('Requested graceful experiment interruption:',found)
