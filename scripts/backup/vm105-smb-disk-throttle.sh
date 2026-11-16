#!/bin/bash
# Cap (or uncap) the write speed of VM 105's SMB data disk (scsi1, on the USB HDD) - applied live, no reboot
#
# Usage: ./vm105-smb-disk-throttle.sh <MB/s | off | status>      e.g. 35
#
# Why (2026-11-16): the guest can write ~140 MB/s into the host's ZFS cache, the USB HDD absorbs ~40 MB/s. The pool's
# dirty-data buffer fills and ZFS parks writers in dmu_tx_wait inside the zvol worker threads, which are SHARED by every
# VM disk, so fsyncs on the NVMe root disk (etcd!) stall for 5-25 s (io-isolation-host-probe.sh: up to 23 of 31 zvol
# threads blocked). A cap at the HDD's real speed keeps the buffer from filling.
# Sets mbps_wr / mbps_wr_max on scsi1 via qm set (idempotent, keeps every other disk option).
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/cloud-backup-common.sh"
ARG="${1:?MB/s, off or status}"
cb_ssh "VMID=$CB_K3S_VMID ARG=$ARG bash -s" <<'EOS'
set -euo pipefail
cur=$(qm config $VMID | sed -n 's/^scsi1: //p')
base=$(echo "$cur" | sed -E 's/,?mbps_(wr|rd)(_max)?=[0-9.]+//g')
case "$ARG" in
  status) echo "scsi1: $cur"; exit 0;;
  off)    new="$base";;
  *)      [[ "$ARG" =~ ^[0-9]+$ ]] || { echo "ERROR: MB/s must be an integer"; exit 1; }
          new="$base,mbps_wr=$ARG,mbps_wr_max=$ARG";;
esac
[[ "$new" == "$cur" ]] && { echo "unchanged: scsi1: $cur"; exit 0; }
qm set $VMID --scsi1 "$new" >/dev/null
echo "scsi1: $(qm config $VMID | sed -n 's/^scsi1: //p')"
qm config $VMID --current 0 | grep -qi pending && echo "NOTE: change is pending (needs VM restart)" || echo "applied live"
EOS
