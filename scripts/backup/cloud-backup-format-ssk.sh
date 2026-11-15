#!/bin/bash
# DESTRUCTIVE: wipe the SSK USB disk on the host and format it exFAT for the secondary copy
#
# Usage: ./cloud-backup-format-ssk.sh --yes
#
# Finds the disk by USB serial ($CB_SSK_SERIAL), never by /dev/sdX name. Refuses if:
#   - no disk or more than one disk has that serial
#   - any partition on it is mounted, or it holds an imported ZFS pool
# Then: clears ZFS labels and signatures, writes a new GPT with one partition, mkfs.exfat -L $CB_SSK_LABEL.
# Installs exfatprogs on the host if needed.
#
# History: first run 2026-11-14 (the disk held an old 2024 `pve` boot pool, inspected before wiping).
# Design: docs/plans/cloud-drive-backup-and-reclaim.md (§4, Phase 4)

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/cloud-backup-common.sh"

[[ "${1:-}" == "--yes" ]] || { echo "Refusing: this erases the SSK disk. Re-run with --yes."; exit 1; }

cb_ssh "SERIAL='$CB_SSK_SERIAL' LABEL='$CB_SSK_LABEL' bash -s" <<'EOF'
set -euo pipefail
mapfile -t DISKS < <(lsblk -dno NAME,SERIAL | awk -v s="$SERIAL" '$2==s {print "/dev/"$1}')
[[ ${#DISKS[@]} -eq 1 ]] || { echo "ERROR: expected 1 disk with serial $SERIAL, found ${#DISKS[@]}"; exit 1; }
D="${DISKS[0]}"
echo "Target: $D  $(lsblk -dno MODEL,SIZE "$D")  serial $SERIAL"
if lsblk -no MOUNTPOINT "$D" | grep -q .; then echo "ERROR: $D has mounted partitions"; exit 1; fi
for p in $(lsblk -lno NAME "$D" | tail -n +2); do
  if zpool status -P 2>/dev/null | grep -q "/dev/$p\b\|by-id/.*$(basename "$p")"; then
    echo "ERROR: /dev/$p belongs to an imported ZFS pool - export it first"; exit 1
  fi
done

for p in $(lsblk -lno NAME "$D" | tail -n +2); do
  zpool labelclear -f "/dev/$p" 2>/dev/null || true
  wipefs -aq "/dev/$p"
done
wipefs -aq "$D"
sgdisk --zap-all "$D" >/dev/null
sgdisk -n1:0:0 -t1:0700 -c1:"$LABEL" "$D" >/dev/null
blockdev --rereadpt "$D"; udevadm settle
command -v mkfs.exfat >/dev/null || DEBIAN_FRONTEND=noninteractive apt-get install -y -qq exfatprogs >/dev/null
mkfs.exfat -L "$LABEL" "${D}1" | tail -1
udevadm settle
blkid "${D}1"
EOF
