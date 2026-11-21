#!/usr/bin/env bash
# Check mounts and services without printing credentials or private filenames.
set -euo pipefail
ssh -o BatchMode=yes "root@${1:-pumped-piglet.maas}" 'bash -s' <<'REMOTE'
set -euo pipefail
echo '=== Proxmox health ==='
systemctl is-active pve-cluster pvedaemon
dpkg --audit
apt-get check -qq
echo '=== Host read-only mounts ==='
findmnt -M /mnt/filebrowser/SSK
findmnt -M /mnt/filebrowser/RASPBMC
findmnt -M /mnt/filebrowser/BitLocker || true
echo '=== Container ==='
pct status 104
pct config 104
pct exec 104 -- systemctl is-active filebrowser
echo '=== Container read-only mount enforcement ==='
labels=(SSK RASPBMC)
if mountpoint -q /mnt/filebrowser/BitLocker; then labels+=(BitLocker); fi
for label in "${labels[@]}"; do
    pct exec 104 -- bash -c 'set -e; target=/srv/files/$1; findmnt -rn -M "$target" -o OPTIONS | grep -Eq "(^|,)ro(,|$)"; if touch "$target/.filebrowser-readonly-probe" 2>/run/filebrowser-probe-error; then rm "$target/.filebrowser-readonly-probe"; echo "FAIL: mount was writable"; exit 1; fi; grep -q "Read-only file system" /run/filebrowser-probe-error; echo "$1: kernel rejected write (EROFS)"' bash "$label"
done
echo '=== Backend HTTP ==='
curl -fsS --max-time 10 http://localhost:8088/ -o /dev/null
echo 'HTTP 200'
echo '=== BitLocker mapping ==='
cryptsetup status filebrowser-bitlocker || true
REMOTE
