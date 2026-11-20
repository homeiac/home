#!/usr/bin/env python3
"""Read-only guest boot, GPU and K3s recovery diagnostics via Proxmox."""
import json
import os
import shlex
import subprocess
script = '''uname -r
uptime
nvidia-smi --query-gpu=name,driver_version,memory.used,utilization.gpu --format=csv
systemctl is-active k3s
ip -br address
journalctl -u k3s -b --no-pager -n 35
'''
command = shlex.join(['qm', 'guest', 'exec', '105', '--', 'bash', '-lc', script])
r = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5',
                    os.environ.get('CB_HOST', 'root@pumped-piglet.maas'), command],
                   text=True, capture_output=True, timeout=45)
if r.returncode:
    print(r.stderr); raise SystemExit(r.returncode)
j = json.loads(r.stdout)
print(j.get('out-data', '')); print(j.get('err-data', ''))
