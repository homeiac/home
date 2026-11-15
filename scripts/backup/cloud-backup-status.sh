#!/bin/bash
# Show the state of the cloud backup: last pull result, sizes, recent jobs, latest log lines
#
# Usage: ./cloud-backup-status.sh
#
# Read-only. Reads /var/lib/cloud-backup/status/last-run.json and the newest log in the K3s VM,
# sizes of each folder under /mnt/samba-storage/cloud-backup, free space, and the Jobs in the
# cloud-backup namespace.

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/cloud-backup-common.sh"

echo "== Jobs"
cb_kubectl -n cloud-backup get cronjob,jobs 2>&1 || true
echo
cb_ssh "qm guest exec $CB_K3S_VMID --timeout 120 -- bash -c '
  echo \"== Last run\"; cat /var/lib/cloud-backup/status/last-run.json 2>/dev/null || echo \"(no completed run yet)\"
  echo; echo \"== Sizes (/mnt/samba-storage/cloud-backup)\"
  du -sh /mnt/samba-storage/cloud-backup/* /mnt/samba-storage/cloud-backup/.versions 2>/dev/null
  df -h /mnt/samba-storage | tail -1
  L=\$(ls -t /var/lib/cloud-backup/status/logs/pull-*.log 2>/dev/null | head -1)
  [ -n \"\$L\" ] && { echo; echo \"== \$L (last 8 lines)\"; tail -8 \"\$L\"; }
  true'" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("out-data",""), d.get("err-data",""))'
