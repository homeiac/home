#!/bin/bash
# Control the USB-disk mirrors on the backup host: run now, status, log
#
# Usage:
#   ./cloud-backup-mirror-ctl.sh run <target>   # start a mirror now (ssk | wd25) and follow it to the end
#   ./cloud-backup-mirror-ctl.sh status         # last result per target, timers, attached disks (read-only)
#   ./cloud-backup-mirror-ctl.sh log <target>   # last 40 lines of the newest log for that target
#
# The mirror is host/cloud-backup-mirror.sh (installed by cloud-backup-install-mirror.sh).
# `run` is safe to repeat: the mirror takes a lock, and copy is incremental. Exit code 0 only if the
# run finished with status ok.

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/cloud-backup-common.sh"
readonly TARGETS="ssk wd25"

usage() { sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; }
need_target() {
  [[ " $TARGETS " == *" ${1:-} "* ]] || { usage; echo "ERROR: target must be one of: $TARGETS"; exit 1; }
}

case "${1:-}" in
  run)
    need_target "${2:-}"; t="$2"; unit="cloud-backup-mirror@$t.service"
    cb_ssh "systemctl start --no-block $unit"
    echo "[$(date +%H:%M:%S)] started $unit on $CB_HOST"
    while true; do
      sleep 30
      st="$(cb_ssh "systemctl is-active $unit" || true)"
      last="$(cb_ssh "L=\$(ls -t $CB_REPORT_DIR/mirror-logs/mirror-$t-*.log 2>/dev/null | head -1); [ -n \"\$L\" ] && tail -1 \"\$L\" | cut -c1-160" || true)"
      echo "[$(date +%H:%M:%S)] $st | $last"
      [[ "$st" == activating || "$st" == active ]] || break
    done
    cb_ssh "cat $CB_REPORT_DIR/mirror-$t-last-run.json"
    cb_ssh "grep -q '\"status\": \"ok\"' $CB_REPORT_DIR/mirror-$t-last-run.json"
    ;;
  status)
    for t in $TARGETS; do
      echo "== $t"; cb_ssh "cat $CB_REPORT_DIR/mirror-$t-last-run.json 2>/dev/null || echo '(no run yet)'"
    done
    echo; echo "== Timers"; cb_ssh "systemctl list-timers 'cloud-backup-mirror@*' --no-pager | head -4" || true
    echo; echo "== Disks"
    cb_ssh "for s in $CB_SSK_SERIAL $CB_WD25_SERIAL; do d=\$(lsblk -dnro NAME,SERIAL | awk -v s=\$s '\$2==s {print \"/dev/\"\$1}'); \
            if [ -n \"\$d\" ]; then lsblk -no NAME,SIZE,FSTYPE,LABEL,MOUNTPOINT \$d; else echo \"serial \$s: not attached\"; fi; done"
    ;;
  log)
    need_target "${2:-}"
    cb_ssh "L=\$(ls -t $CB_REPORT_DIR/mirror-logs/mirror-$2-*.log 2>/dev/null | head -1); [ -n \"\$L\" ] && { echo \"== \$L\"; tail -40 \"\$L\"; } || echo '(no log yet)'"
    ;;
  -h|--help) usage;;
  *) usage; exit 1;;
esac
