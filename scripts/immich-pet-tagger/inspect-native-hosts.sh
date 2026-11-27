#!/usr/bin/env bash
# Read-only capacity check on the two inventory-verified Proxmox hosts, not their VMs.
set -euo pipefail
for host in fun-bedbug.maas chief-horse.maas; do
  ssh -T -o BatchMode=yes -o ConnectTimeout=10 "root@$host" 'bash -s' <<'REMOTE'
set -eu
hostname
uname -m
nproc
cat /proc/loadavg
free -m
df -h /var/lib /opt
command -v python3 uv docker podman systemctl || true
python3 --version
qm list
pct list
if command -v sensors >/dev/null; then sensors; fi
REMOTE
done
