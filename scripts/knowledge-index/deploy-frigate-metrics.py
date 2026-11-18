#!/usr/bin/env python3
"""Install the bounded Frigate stats poller on an inventory-selected host (#217).

Usage: CB_HOST=root@<inventory-address> python3 scripts/knowledge-index/deploy-frigate-metrics.py
Uses existing SSH authentication, backs up prior source/unit files, never restarts Frigate.
"""
import json
import os
from pathlib import Path
import shlex
import subprocess


def main() -> None:
    """Transfer reviewed sources over SSH and verify textfile publication."""
    here = Path(__file__).resolve().parent
    payload = {"export-frigate-metrics.py": (here/"export-frigate-metrics.py").read_text(),
               "knowledge-index-frigate-metrics.service": (here/"host/knowledge-index-frigate-metrics.service").read_text()}
    remote = r'''
import datetime,json,pathlib,shutil,subprocess,sys,time
payload=json.load(sys.stdin)
backup=pathlib.Path('/var/backups/knowledge-index-frigate-metrics')/datetime.datetime.now().strftime('%Y%m%dT%H%M%S')
backup.mkdir(parents=True)
paths={'export-frigate-metrics.py':pathlib.Path('/opt/knowledge-index/export-frigate-metrics.py'),
       'knowledge-index-frigate-metrics.service':pathlib.Path('/etc/systemd/system/knowledge-index-frigate-metrics.service')}
unit='knowledge-index-frigate-metrics.service'
active=subprocess.run(['systemctl','is-active','--quiet',unit]).returncode==0
enabled=subprocess.run(['systemctl','is-enabled','--quiet',unit]).returncode==0
started=time.time()
existed={name:path.exists() for name,path in paths.items()}
for name,path in paths.items():
    if path.exists(): shutil.copy2(path,backup/name)
print('Backup:',backup,flush=True)
try:
    for name,path in paths.items():
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(payload[name]);path.chmod(0o644)
    subprocess.run(['systemctl','daemon-reload'],check=True)
    subprocess.run(['systemctl','enable',unit],check=True)
    subprocess.run(['systemctl','restart',unit],check=True)
    output=pathlib.Path('/var/lib/prometheus/node-exporter/knowledge_index_frigate.prom')
    for _ in range(20):
        if output.exists() and output.stat().st_mtime>=started: break
        time.sleep(1)
    else: raise RuntimeError('No fresh Frigate textfile output')
    subprocess.run(['systemctl','is-active',unit],check=True)
    print('Frigate processing telemetry published; camera and summary services unchanged')
except BaseException:
    subprocess.run(['systemctl','stop',unit])
    if not enabled: subprocess.run(['systemctl','disable',unit])
    for name,path in paths.items():
        if existed[name]: shutil.copy2(backup/name,path)
        else: path.unlink(missing_ok=True)
    subprocess.run(['systemctl','daemon-reload'])
    if active: subprocess.run(['systemctl','start',unit])
    raise
'''
    subprocess.run(["ssh","-o","BatchMode=yes","-o","ConnectTimeout=10",os.environ["CB_HOST"],
                    "python3 -c "+shlex.quote(remote)],input=json.dumps(payload),text=True,check=True)


if __name__ == '__main__':
    main()
