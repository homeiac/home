#!/usr/bin/env python3
"""Operate private video trials on the inventory-selected existing host."""
import argparse
from pathlib import Path
import shlex
import subprocess

HERE=Path(__file__).resolve().parent
REMOTE='/opt/knowledge-index/video-tuning/trial-next.py'
STATE='/local-3TB-backup/photo-enrichment/video-tuning-20261124'
PYTHON='/opt/knowledge-index/venv/bin/python'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host',required=True,help='Verified Proxmox host from proxmox/inventory.txt')
    p.add_argument('mode',choices=('install','run','report','audit-snapshot','audit-verify'))
    p.add_argument('--profiles',default='safe8,safe4')
    p.add_argument('--backends',default='rtx,mac')
    p.add_argument('--block',type=int,default=2)
    p.add_argument('--parallel',type=int,default=1)
    p.add_argument('--reset-rtx',action='store_true')
    a=p.parse_args()
    ssh=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10',a.host]
    if a.mode=='install':
        subprocess.run(ssh+['umask 077; cat > '+REMOTE],input=(HERE/'trial.py').read_bytes(),check=True)
    elif a.mode.startswith('audit-'):
        script=HERE.parent/'caption-gitops/audit.py'
        mode=a.mode.removeprefix('audit-')
        subprocess.run(ssh+[PYTHON+' - '+mode+' /var/tmp/video-tuning-caption-baseline.json'],input=script.read_bytes(),check=True)
    else:
        args=[PYTHON,REMOTE,'--state',STATE]
        if a.mode=='report':args+=['--report']
        else:args+=['--profiles',a.profiles,'--backends',a.backends,'--block',str(a.block),'--parallel',str(a.parallel)]
        if a.reset_rtx:args.append('--reset-rtx')
        subprocess.run(ssh+[shlex.join(args)],check=True)

if __name__=='__main__':main()
