#!/usr/bin/env python3
"""Gracefully stop only this Waffles experiment, allowing its restoration finally block."""
import os
import argparse
from pathlib import Path
import shlex
import signal
import subprocess

parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--continuous',action='store_true');args=parser.parse_args()
target=['scripts/immich-pet-tagger/'+('continuous-experiment.py' if args.continuous else 'experiment.py'),'/private/tmp/waffles-pet-tagger-private']
found=[]
for line in subprocess.check_output(['ps','-axo','pid=,args='],text=True).splitlines():
    pid,command=line.strip().split(None,1)
    try:args=shlex.split(command)
    except ValueError:continue
    if len(args)==3 and args[1:]==target and 'python' in Path(args[0]).name.lower():
        os.kill(int(pid),signal.SIGTERM);found.append(int(pid))
print('Requested graceful experiment interruption:',found)
