#!/bin/bash
# VM 105: per-disk I/O isolation (virtio-scsi-single + iothreads) + virtiofs for the host Photos dataset
#
# Usage: ./vm105-disk-isolation.sh [--no-reboot]
#
# Idempotent. On $CB_HOST:
#   1. backs up /etc/pve/qemu-server/105.conf to /root/105.conf.bak-<time>
#   2. creates ZFS dataset local-3TB-backup/gphotos (recordsize=1M, lz4, atime=off) if missing
#      and Proxmox directory mapping "gphotos" -> its mountpoint on this node
#   3. qm set: scsihw virtio-scsi-single; scsi1 (SMB disk) iothread=1 (scsi0 already has it - with
#      virtio-scsi-pci both were ignored); virtiofs1 = gphotos (cache=auto: the host writes, VM reads)
#   4. unless --no-reboot: clean shutdown (guest agent/ACPI, 300 s) and start with a 600 s timeout
#      (GPU passthrough pins all 32 GB at start; the default timeout was too short on 2026-11-15)
# Why: scripts/k3s/io-isolation-test.sh on 2026-11-16 - etcd-style fsync on the root disk: baseline
# max 2 ms, while streaming to the SMB disk p99 4.2 s / max 13.9 s (one shared controller, no iothreads).
# Rerun that test after the reboot. Revert: restore the backup conf, reboot.

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/cloud-backup-common.sh"
VMID=105 DS=local-3TB-backup/gphotos MAP=gphotos
REBOOT=1; [[ "${1:-}" == --no-reboot ]] && REBOOT=0

cb_ssh "VMID=$VMID DS=$DS MAP=$MAP REBOOT=$REBOOT bash -s" <<'EOS'
set -euo pipefail
CONF=/etc/pve/qemu-server/$VMID.conf
cp -a "$CONF" "/root/$VMID.conf.bak-$(date +%Y%m%d-%H%M%S)"
zfs list -H "$DS" >/dev/null 2>&1 || { zfs create -o recordsize=1M -o compression=lz4 -o atime=off "$DS"; echo "created $DS"; }
MP=$(zfs get -H -o value mountpoint "$DS")
if ! pvesh get /cluster/mapping/dir --output-format json | python3 -c "import json,sys; sys.exit(0 if any(m['id']=='$MAP' for m in json.load(sys.stdin)) else 1)"; then
  pvesh create /cluster/mapping/dir --id "$MAP" --map "node=$(hostname),path=$MP"; echo "created directory mapping $MAP -> $MP"
fi
grep -q '^scsihw: virtio-scsi-single' "$CONF" || { qm set $VMID --scsihw virtio-scsi-single >/dev/null; echo "scsihw -> virtio-scsi-single"; }
s1=$(sed -n 's/^scsi1: //p' "$CONF")
[[ "$s1" == *iothread=1* ]] || { qm set $VMID --scsi1 "$s1,iothread=1" >/dev/null; echo "scsi1 -> $s1,iothread=1"; }
grep -q "^virtiofs1: $MAP" "$CONF" || { qm set $VMID --virtiofs1 "$MAP,cache=auto" >/dev/null; echo "virtiofs1 -> $MAP"; }
echo "--- config now (pending until restart if shown under [pending]):"
qm config $VMID --current 0 | grep -E '^(scsihw|scsi[01]|virtiofs[0-9])'
[[ $REBOOT == 1 ]] || exit 0
if [[ "$(qm status $VMID | awk '{print $2}')" == running ]]; then
  echo "--- $(date -u +%T) clean shutdown"
  qm shutdown $VMID --timeout 300 --forceStop 1
else
  echo "--- VM already stopped"
fi
echo "--- $(date -u +%T) start (timeout 600 s)"
qm start $VMID --timeout 600
qm status $VMID; date -u +%T
EOS
