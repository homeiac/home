#!/usr/bin/env python3
"""Read-only reachability and VM status during the GPU maintenance reboot."""
import concurrent.futures
import json
import socket
import subprocess

# Addresses verified in proxmox/inventory.txt.
checks = [('piglet-host', '192.168.4.175', 22),
          ('piglet-api', '192.168.4.210', 6443),
          ('fawn-host', '192.168.4.17', 22),
          ('fawn-api', '192.168.4.212', 6443)]
def check(item):
    name, address, port = item
    try:
        with socket.create_connection((address, port), timeout=5):
            return {'name': name, 'reachable': True}
    except OSError as error:
        return {'name': name, 'reachable': False, 'error': str(error)}
with concurrent.futures.ThreadPoolExecutor() as pool:
    for result in pool.map(check, checks):
        print(json.dumps(result), flush=True)
r = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5',
                    'root@192.168.4.175', 'uptime; qm status 105'],
                   text=True, capture_output=True, timeout=15)
print(json.dumps({'host_status': r.stdout, 'error': r.stderr, 'code': r.returncode}))
