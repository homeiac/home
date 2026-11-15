#!/bin/bash
# Tune the SMB share's zvol for large streaming writes (idempotent, live, reversible)
#
# Usage: ./cloud-backup-tune-zvol.sh            # apply
#        ./cloud-backup-tune-zvol.sh --check    # show current values only
#
# Sets logbias=throughput on $CB_ZVOL. Why (2026-11-15): with the default logbias=latency and no
# separate log device, every flush from the VM's ext4 forced ZFS to write the data into the intent
# log (ZIL) on the same USB HDD and then again into the pool. Eight parallel 50 GB Takeout downloads
# made txg_sync block for >120 s, the K3s node went NotReady and its pods were evicted.
# throughput: large synchronous writes go straight to their final location (no double write).
# Durability is unchanged (sync stays "standard"). Revert: zfs set logbias=latency <zvol>.

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/cloud-backup-common.sh"
cur="$(cb_ssh "zfs get -H -o value logbias '$CB_ZVOL'")"
echo "$CB_ZVOL: logbias=$cur sync=$(cb_ssh "zfs get -H -o value sync '$CB_ZVOL'")"
[[ "${1:-}" == --check ]] && exit 0
if [[ "$cur" == throughput ]]; then echo "already logbias=throughput - nothing to do"; exit 0; fi
cb_ssh "zfs set logbias=throughput '$CB_ZVOL'"
echo "set logbias=throughput (now: $(cb_ssh "zfs get -H -o value logbias '$CB_ZVOL'"))"
