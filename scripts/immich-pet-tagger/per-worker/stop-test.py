#!/usr/bin/env python3
"""Stop only the explicitly named isolated benchmark process after a failed trial."""
import argparse,os,signal,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('trial',type=Path);a=p.parse_args();pid=int((a.trial/'pid').read_text());command=subprocess.check_output(['ps','-p',str(pid),'-o','command='],text=True)
assert str(a.trial.parent/'worker.py') in command and '--label '+a.trial.name in command
os.kill(pid,signal.SIGTERM)
print('Stopped failed isolated diagnostic',a.trial.name,pid)
