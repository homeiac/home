#!/bin/bash
# Grow the SMB share's disk (VM 105 scsi1, ext4 at /mnt/samba-storage) online, to an absolute size
#
# Usage: ./cloud-backup-grow-smb-disk.sh <size-in-GB>      e.g. 600
#
# Steps:
#   1. preflight on the host: the VM disk is the zvol $CB_ZVOL, the pool has room for the growth
#   2. preflight in the VM: the filesystem mounted at /mnt/samba-storage is ext4 labelled smb_data
#      (found by mountpoint, never by /dev name)
#   3. qm resize <vmid> scsi1 <size>G   (ZFS zvol grows; thin, no reservation)
#   4. in the VM: rescan the SCSI disk, resize2fs online (Samba keeps serving)
#   5. print df before/after
# Idempotent: does nothing if the disk is already >= the requested size. Never shrinks.
# Why 600G (2026-11-15): Google Photos Takeout is 306 GB; extraction needs one archive (<=50 GB)
# of staging on top. Pool local-3TB-backup is shared with PBS - check its free space first.
# Design: docs/plans/cloud-drive-backup-and-reclaim.md (§10 Capacity)

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/cloud-backup-common.sh"

readonly WANT_GB="${1:?usage: $0 <size-in-GB>}"
[[ "$WANT_GB" =~ ^[0-9]+$ ]] || { echo "ERROR: size must be a number of GB"; exit 1; }
readonly MNT=/mnt/samba-storage LABEL=smb_data

cb_ssh "VMID='$CB_K3S_VMID' ZVOL='$CB_ZVOL' WANT_GB='$WANT_GB' MNT='$MNT' LABEL='$LABEL' bash -s" <<'EOF'
set -euo pipefail
gx() { qm guest exec "$VMID" --timeout 120 -- bash -c "$1" | python3 -c 'import json,sys
d=json.load(sys.stdin); sys.stdout.write(d.get("out-data","")); sys.stderr.write(d.get("err-data","")); sys.exit(d.get("exitcode",1))'; }

# 1. host side
line="$(qm config "$VMID" | grep '^scsi1:')"
[[ "$line" == *"${ZVOL#*/}"* ]] || { echo "ERROR: scsi1 is not $ZVOL: $line"; exit 1; }
cur_b=$(zfs get -Hp -o value volsize "$ZVOL"); want_b=$(( WANT_GB * 1024 * 1024 * 1024 ))
echo "zvol $ZVOL: $((cur_b / 1073741824)) GiB now, want $WANT_GB GiB"
avail=$(zfs get -Hp -o value available "${ZVOL%%/*}")
echo "pool ${ZVOL%%/*}: $((avail / 1073741824)) GiB available"
if (( cur_b >= want_b )); then echo "already >= $WANT_GB GiB - nothing to do"; RESIZED=0
else
  # Thin zvol (no refreservation): growing volsize uses no space; filling it does. Refuse if filling
  # the whole disk would take more than 75% of what the pool has free (the pool is shared with PBS).
  # A reserved zvol would claim the growth immediately: then the growth itself must fit.
  used=$(zfs get -Hp -o value used "$ZVOL"); resv=$(zfs get -H -o value refreservation "$ZVOL")
  if [[ "$resv" == none ]]; then
    worst=$(( want_b - used ))
    echo "thin zvol: filling it completely would need $((worst / 1073741824)) GiB more"
    (( worst < avail * 3 / 4 )) || { echo "ERROR: a full disk would use >75% of the pool's free space"; exit 1; }
  else
    (( want_b - cur_b < avail )) || { echo "ERROR: reserved zvol growth does not fit the pool"; exit 1; }
  fi
  RESIZED=1
fi

# 2. guest side: which device is the share?
DEV="$(gx "findmnt -no SOURCE $MNT")"; DEV="${DEV//$'\n'/}"
info="$(gx "lsblk -no FSTYPE,LABEL $DEV")"
[[ "$info" == *ext4*"$LABEL"* ]] || { echo "ERROR: $MNT is $DEV ($info), expected ext4 $LABEL"; exit 1; }
echo "before: $(gx "df -h --output=size,used,avail $MNT | tail -1")  ($DEV)"

# 3 + 4
if [[ $RESIZED -eq 1 ]]; then
  qm resize "$VMID" scsi1 "${WANT_GB}G"
fi
gx "echo 1 > /sys/class/block/$(basename "$DEV")/device/rescan; sleep 2; resize2fs $DEV 2>&1 | tail -2"
echo "after:  $(gx "df -h --output=size,used,avail $MNT | tail -1")"
EOF
