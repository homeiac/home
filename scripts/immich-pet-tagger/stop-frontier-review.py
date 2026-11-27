#!/usr/bin/env python3
"""Stop only a named frontier review after a quality failure; preserve intent files."""
import argparse
import os
import signal
import subprocess
p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory');p.add_argument('--model',required=True);a=p.parse_args()
rows=subprocess.check_output(['ps','-axo','pid=,command='],text=True).splitlines()
for row in rows:
 pid,command=row.strip().split(None,1)
 if 'frontier-review.py review '+a.directory in command and '--model '+a.model in command and 'python' in command.lower() and 'stop-frontier-review' not in command:
  os.kill(int(pid),signal.SIGTERM);print('Stopped matching review process',pid)
