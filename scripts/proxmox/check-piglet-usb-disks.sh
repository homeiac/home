#!/usr/bin/env bash
# Read-only inventory of USB filesystems and possible web file browsers on piglet.
# Uses existing SSH authentication; never mounts disks or changes host settings.
set -euo pipefail

# Optional first argument is a verified inventory address when local DNS is unavailable.
ssh -o BatchMode=yes -o ConnectTimeout=10 "root@${1:-pumped-piglet.maas}" 'bash -s' <<'REMOTE'
set -euo pipefail
echo '=== Disks and filesystems ==='
lsblk -o NAME,TRAN,SIZE,FSTYPE,LABEL,UUID,MOUNTPOINTS,MODEL
echo '=== Windows filesystem mounts ==='
findmnt -t ntfs,ntfs3,fuseblk,exfat,vfat || true
echo '=== Containers ==='
pct list
echo '=== Virtual machines ==='
qm list
echo '=== File browser services ==='
systemctl list-units --all --type=service --no-pager | grep -Ei 'filebrowser|cockpit|smb|nginx|caddy' || true
echo '=== Disk and USB passthrough configuration ==='
grep -HE '^(usb[0-9]+|mp[0-9]+):|^((scsi|sata|virtio)[0-9]+): /dev/' /etc/pve/qemu-server/*.conf /etc/pve/lxc/*.conf || true
REMOTE
