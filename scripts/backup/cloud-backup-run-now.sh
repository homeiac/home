#!/bin/bash
# Start the cloud-drive-pull backup job now (instead of waiting for 02:30) and follow it
#
# Usage: ./cloud-backup-run-now.sh [--no-follow]
#
# Creates Job cloud-drive-pull-manual-<timestamp> from the CronJob. Refuses if a pull Job is
# already running (same rule as the CronJob's concurrencyPolicy: Forbid). Then prints the
# progress lines from the pod every 30 s until the Job finishes. Best run in the background;
# progress is also in /var/lib/cloud-backup/status/logs/ in the K3s VM (cloud-backup-status.sh).

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/cloud-backup-common.sh"
readonly NS=cloud-backup

running="$(cb_kubectl -n "$NS" get jobs -o jsonpath='{range .items[?(@.status.active)]}{.metadata.name}{" "}{end}' 2>/dev/null | tr ' ' '\n' | grep '^cloud-drive-pull' || true)"
if [[ -n "$running" ]]; then echo "Already running: $running"; JOB="${running%%$'\n'*}"
else
  JOB="cloud-drive-pull-manual-$(date +%Y%m%d-%H%M%S)"
  cb_kubectl -n "$NS" create job "$JOB" --from=cronjob/cloud-drive-pull
fi
[[ "${1:-}" == "--no-follow" ]] && exit 0

echo "[$(date +%H:%M:%S)] following $JOB"
while true; do
  st="$(cb_kubectl -n "$NS" get job "$JOB" -o jsonpath='{.status.succeeded}/{.status.failed}/{.status.active}' 2>&1 || true)"
  echo "[$(date +%H:%M:%S)] succeeded/failed/active = $st"
  cb_kubectl -n "$NS" logs "job/$JOB" --tail=3 2>&1 | sed 's/^/    /' || true
  case "$st" in
    1/*) echo "Job succeeded"; exit 0;;
    */[1-9]*/) echo "Job failed"; cb_kubectl -n "$NS" logs "job/$JOB" --tail=40 || true; exit 1;;
  esac
  sleep 30
done
