#!/usr/bin/env python3
"""Inspect VM 105 driver packages via the Proxmox guest agent, never VM SSH."""
import json
import os
import shlex
import subprocess
host=os.environ.get('CB_HOST','root@pumped-piglet.maas')
script='''cat /etc/os-release
uname -r
apt-cache policy nvidia-driver-535 nvidia-driver-550 nvidia-driver-570 nvidia-driver-580
 dpkg-query -W -f='${Package} ${Version}\\n' '*nvidia*' 'linux-headers*' 2>/dev/null
apt-mark showhold
df -h /boot /
command -v mokutil >/dev/null && mokutil --sb-state || true
'''
command=shlex.join(['qm','guest','exec','105','--','bash','-lc',script])
result=subprocess.run(['ssh','-o','BatchMode=yes',host,command],text=True,capture_output=True,check=True)
parsed=json.loads(result.stdout)
print(json.dumps(parsed))
