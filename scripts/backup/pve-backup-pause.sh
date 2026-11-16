#!/bin/bash
# Pause / resume the scheduled Proxmox VM backup job (vzdump to PBS)
#
# Usage: ./pve-backup-pause.sh status | pause | resume [job-id]
#   default job-id: backup-ff3d789f-f52b (all guests except 103,108, 02:30 + 22:30, snapshot mode)
#
# pause : disables the job (cluster-wide: no new runs on ANY node) and stops vzdump runs already
#         in progress on $CB_HOST (the unfinished PBS snapshot is discarded; earlier backups stay).
# resume: re-enables the job; the next scheduled run happens as usual.
# status: job enabled? + running vzdump tasks.
#
# Why (2026-11-15): the 22:30 run backed up VM 105 including its 600G SMB disk, reading from and
# writing PBS onto the same USB-HDD pool while Photos Takeout downloads + ingest were running; its
# snapshot-mode fs-freeze/thaw took minutes and the VM's workloads hung. Pause during heavy
# backup-disk work; resume afterwards.

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/cloud-backup-common.sh"
ACTION="${1:-status}"; JOB="${2:-backup-ff3d789f-f52b}"

status() {
  cb_ssh "pvesh get /cluster/backup/$JOB --output-format json" | python3 -c 'import json,sys
j=json.load(sys.stdin); print("job %s: enabled=%s schedule=%s storage=%s" % (j["id"], j.get("enabled",1), j.get("schedule"), j.get("storage")))'
  cb_ssh "ps -eo etime,args | grep -o '[ 0-9:-]*task UPID:[^ ]*vzdump[^ ]*' || echo '  no vzdump running on this host'"
}
case "$ACTION" in
  status) status;;
  pause)
    cb_ssh "pvesh set /cluster/backup/$JOB --enabled 0"
    echo "disabled $JOB (cluster-wide)"
    for u in $(cb_ssh "ps -eo args | grep -o 'UPID:[^ ]*vzdump[^ ]*' || true"); do
      node="$(cut -d: -f2 <<<"$u")"
      cb_ssh "pvesh delete '/nodes/$node/tasks/$u'" && echo "stopped running $u"
    done
    status;;
  resume)
    cb_ssh "pvesh set /cluster/backup/$JOB --enabled 1"
    echo "re-enabled $JOB"; status;;
  *) sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 1;;
esac
