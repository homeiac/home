#!/bin/bash
# Control the SSK mirror on the backup host: run now, status, log
#
# Usage:
#   ./cloud-backup-mirror-ctl.sh run      # start a mirror now and follow it until it finishes
#   ./cloud-backup-mirror-ctl.sh status   # last result, timer, SSK contents (read-only)
#   ./cloud-backup-mirror-ctl.sh log      # last 40 lines of the newest mirror log
#
# The mirror itself is host/cloud-backup-mirror.sh (installed by cloud-backup-install-mirror.sh).
# `run` is safe to repeat: the mirror takes a lock, and copy is incremental.

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/cloud-backup-common.sh"

latest_log='ls -t '"$CB_REPORT_DIR"'/mirror-logs/mirror-*.log 2>/dev/null | head -1'

case "${1:-}" in
  run)
    cb_ssh "systemctl start --no-block cloud-backup-mirror.service"
    echo "[$(date +%H:%M:%S)] started cloud-backup-mirror.service on $CB_HOST"
    while true; do
      sleep 30
      st="$(cb_ssh "systemctl is-active cloud-backup-mirror.service" || true)"
      echo "[$(date +%H:%M:%S)] $st | $(cb_ssh "L=\$($latest_log); [ -n \"\$L\" ] && tail -1 \"\$L\" | cut -c1-160" || true)"
      [[ "$st" == activating || "$st" == active ]] || break
    done
    cb_ssh "cat $CB_REPORT_DIR/mirror-last-run.json"
    cb_ssh "grep -q '\"status\": \"ok\"' $CB_REPORT_DIR/mirror-last-run.json"
    ;;
  status)
    cb_ssh "echo '== Last run'; cat $CB_REPORT_DIR/mirror-last-run.json 2>/dev/null || echo '(none yet)'
            echo; echo '== Timer'; systemctl list-timers cloud-backup-mirror.timer --no-pager | head -2
            echo; echo '== SSK'; lsblk -no NAME,SIZE,FSTYPE,LABEL,MOUNTPOINT \$(lsblk -dnro NAME,SERIAL | awk '\$2==\"$CB_SSK_SERIAL\" {print \"/dev/\"\$1}') 2>/dev/null || echo 'SSK not attached'"
    ;;
  log)
    cb_ssh "L=\$($latest_log); [ -n \"\$L\" ] && { echo \"== \$L\"; tail -40 \"\$L\"; } || echo '(no mirror log yet)'"
    ;;
  *) sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 1;;
esac
