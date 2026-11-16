#!/bin/bash
# Run / watch the host-side Google Photos ingest (scripts/backup/host/gphotos-ingest-host.sh)
#
# Usage:
#   ./gphotos-ingest-ctl.sh start [archive-filter]   # install script, start as transient systemd unit
#   ./gphotos-ingest-ctl.sh status                   # unit state, last-run JSON, ledger, last log lines
#   ./gphotos-ingest-ctl.sh stop                     # stop the unit (cleanup trap removes clones/staging)
#
# Runs on $CB_HOST as systemd unit "gphotos-ingest" (survives SSH disconnects), nice 10, idle I/O class.
# archive-filter: substring, e.g. "1-006" to ingest just that archive (smoke test). Idempotent: already
# ingested archives are skipped.

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/cloud-backup-common.sh"
HOST_SCRIPT="$(dirname "${BASH_SOURCE[0]}")/host/gphotos-ingest-host.sh"
case "${1:-}" in
  start)
    cb_ssh "install -m 0755 /dev/stdin /usr/local/sbin/gphotos-ingest-host.sh" < "$HOST_SCRIPT"
    # knowledge index (#212): the ingest calls /opt/knowledge-index/index-unit.sh; install it (and the adapter) first
    "$(dirname "${BASH_SOURCE[0]}")/../knowledge-index/knowledge-index-ctl.sh" install
    cb_ssh "systemctl is-active -q gphotos-ingest && { echo 'already running'; exit 0; }; systemctl reset-failed gphotos-ingest 2>/dev/null; \
            systemd-run --unit=gphotos-ingest --collect -p Nice=10 -p IOSchedulingClass=idle \
              --setenv=ARCHIVE_FILTER='${2:-}' /usr/local/sbin/gphotos-ingest-host.sh && echo started"
    ;;
  status)
    cb_ssh "echo \"unit: \$(systemctl is-active gphotos-ingest 2>/dev/null)\"; D=\$(zfs get -H -o value mountpoint local-3TB-backup/gphotos 2>/dev/null); \
            [ -n \"\$D\" ] && { cat \"\$D/_last-run.json\" 2>/dev/null; echo \"ledger: \$(wc -l < \$D/_ingested.tsv 2>/dev/null || echo 0) archives\"; zfs list -o name,used,avail local-3TB-backup/gphotos; }; \
            L=\$(ls -t /var/lib/cloud-backup/reports/gphotos-ingest-*.log 2>/dev/null | head -1); [ -n \"\$L\" ] && tail -6 \"\$L\""
    ;;
  stop) cb_ssh "systemctl stop gphotos-ingest && echo stopped";;
  *) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 1;;
esac
