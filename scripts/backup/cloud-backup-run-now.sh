#!/bin/bash
# Start the cloud-drive-pull backup job now (instead of waiting for 02:30) and follow it
#
# Usage: ./cloud-backup-run-now.sh [--job <cronjob>] [--restart] [--no-follow]
#   --job       cloud-drive-pull (default) or photos-takeout-ingest
#   --restart   stop a running pull Job first (e.g. to pick up new settings). Safe: rclone copy is
#               resumable, files already copied are skipped on the next run.
#
# Creates Job cloud-drive-pull-manual-<timestamp> from the CronJob. Refuses if a pull Job is
# already running (same rule as the CronJob's concurrencyPolicy: Forbid). Then prints the
# progress lines from the pod every 30 s until the Job finishes. Best run in the background;
# progress is also in /var/lib/cloud-backup/status/logs/ in the K3s VM (cloud-backup-status.sh).

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/cloud-backup-common.sh"
readonly NS=cloud-backup

RESTART=0 FOLLOW=1 CJ=cloud-drive-pull
while [[ $# -gt 0 ]]; do
  case "$1" in
    --restart) RESTART=1;;
    --job) CJ="${2:?--job needs a name}"; shift;;
    --no-follow) FOLLOW=0;;
    *) echo "ERROR: unknown option $1"; exit 1;;
  esac
  shift
done

running="$(cb_kubectl -n "$NS" get jobs -o jsonpath='{range .items[?(@.status.active)]}{.metadata.name}{" "}{end}' 2>/dev/null | tr ' ' '\n' | grep "^$CJ" || true)"
if [[ -n "$running" && $RESTART -eq 1 ]]; then
  for j in $running; do echo "Stopping $j"; cb_kubectl -n "$NS" delete job "$j" --wait=true; done
  running=""
fi
if [[ -n "$running" ]]; then echo "Already running: $running (use --restart to replace it)"; JOB="${running%%$'\n'*}"
else
  JOB="$CJ-manual-$(date +%Y%m%d-%H%M%S)"
  cb_kubectl -n "$NS" create job "$JOB" --from=cronjob/$CJ
fi
[[ $FOLLOW -eq 1 ]] || exit 0

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
