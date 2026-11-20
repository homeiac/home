#!/usr/bin/env python3
"""Reboot VM 105 through its guest agent after the Flux driver Job succeeds.

No VM SSH, new credentials, hostPID, or persistent access changes. Verify the
GitOps install marker and both kernel modules before scheduling the one reboot.
"""
import json
import os
import shlex
import subprocess

host = os.environ.get('CB_HOST', 'root@pumped-piglet.maas')
script = '''set -eu
state=/var/lib/homelab-gpu-driver/580.178.04
[ -f "$state/installed" ]
[ "$(modinfo -k 6.8.0-94-generic -F version nvidia)" = 580.178.04 ]
[ "$(modinfo -k 6.8.0-100-generic -F version nvidia)" = 580.178.04 ]
if [ "$(cat /sys/module/nvidia/version)" = 580.178.04 ]; then
  echo 'Desired driver already loaded; no reboot needed'
  exit 0
fi
systemd-run --unit=homelab-nvidia-580-reboot --on-active=30s /usr/bin/systemctl reboot
'''
command = shlex.join(['qm', 'guest', 'exec', '105', '--', 'bash', '-lc', script])
result = subprocess.run(['ssh', '-o', 'BatchMode=yes', host, command], text=True,
                        capture_output=True, check=True)
parsed = json.loads(result.stdout)
print(json.dumps(parsed))
if parsed.get('exitcode', 0):
    raise SystemExit(parsed['exitcode'])
