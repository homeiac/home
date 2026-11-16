#!/bin/bash
# Repair corrupt Takeout archives by re-fetching only their missing byte ranges (no browser, no VM)
#
# Usage: ./takeout-repair-ctl.sh <part-id|all> [--dry-run]       e.g. 1-002
#   Needs VM $CB_K3S_VMID STOPPED (the host mounts its disks read-write to patch the file in place).
#   --dry-run: list the holes of every archive, no link needed.
#   Otherwise needs /root/.takeout-curl-<part-id> on the host (0600), from Chrome "Copy as cURL" of that part's
#   download; send it with:  pbpaste | ssh root@<host> 'umask 077; cat > /root/.takeout-curl-1-002'
# See host/takeout-range-repair.py for what is checked (HTTP 206 + exact length, final gzip -t).

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/cloud-backup-common.sh"
PART="${1:?part id like 1-002, or all}"; MODE="${2:-}"
PY="$(dirname "${BASH_SOURCE[0]}")/host/takeout-range-repair.py"
cb_ssh "install -m 0755 /dev/stdin /usr/local/sbin/takeout-range-repair.py" < "$PY"
cb_ssh "set -e; [ \"\$(qm status $CB_K3S_VMID | awk '{print \$2}')\" = stopped ] || { echo 'ERROR: VM $CB_K3S_VMID must be stopped'; exit 1; }
  mkdir -p /mnt/repair-a /mnt/repair-b
  mount -t ext4 /dev/zvol/local-2TB-zfs/vm-105-disk-1-part1 /mnt/repair-a
  mount -t ext4 /dev/zvol/local-3TB-backup/vm-105-disk-0 /mnt/repair-b
  trap 'umount /mnt/repair-a /mnt/repair-b 2>/dev/null; rmdir /mnt/repair-a /mnt/repair-b 2>/dev/null' EXIT
  rc=0
  for f in /mnt/repair-a/var/lib/cloud-backup/downloads/*.tgz /mnt/repair-b/cloud-backup/gphotos/_incoming/*.tgz; do
    [ -s \"\$f\" ] || continue
    case \"\$f\" in *-$PART.tgz|*) ;; esac
    if [ '$PART' != all ] && [[ \"\$f\" != *-$PART.tgz ]]; then continue; fi
    if [ -n '$MODE' ]; then python3 /usr/local/sbin/takeout-range-repair.py \"\$f\" --dry-run
    else
      n=\$(python3 /usr/local/sbin/takeout-range-repair.py \"\$f\" --dry-run | grep -o '[0-9]* hole' | cut -d' ' -f1)
      [ \"\${n:-0}\" = 0 ] && { echo \"\$(basename \$f): no holes\"; continue; }
      python3 /usr/local/sbin/takeout-range-repair.py \"\$f\" --curl-file /root/.takeout-curl-\$(basename \$f .tgz | sed 's/.*Z-//') || rc=1
    fi
  done; exit \$rc"
