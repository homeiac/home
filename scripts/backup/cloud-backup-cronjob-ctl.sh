#!/bin/bash
# Suspend / resume a cloud-backup CronJob (and stop its running Job), without touching git
#
# Usage: ./cloud-backup-cronjob-ctl.sh suspend|resume|status <cronjob>
#        e.g. suspend photos-takeout-ingest
#
# suspend: sets spec.suspend=true and deletes the CronJob's active Jobs (their pods get SIGTERM; the
#          ingest's extract.sh trap removes partial staging; archives stay and are retried later).
# resume : sets spec.suspend=false; the next scheduled run happens as usual.
# TEMPORARY: Flux re-applies the CronJob from git and was observed (2026-11-16) to reset `suspend`
# within minutes. Use this for short pauses and re-check with `status`; for a lasting suspend, set
# `spec.suspend: true` in gitops/clusters/homelab/apps/cloud-backup/<job>/cronjob.yaml.
# Why (2026-11-16): the ingest's HDD-to-HDD unpack of a 38 GB archive slowed etcd (apply >700 ms) and
# made the K3s node flap NotReady while the Photos downloads were still running.

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/cloud-backup-common.sh"
ACTION="${1:-}"; CJ="${2:-}"; NS=cloud-backup
[[ -n "$CJ" && "$ACTION" =~ ^(suspend|resume|status)$ ]] || { sed -n '2,6p' "$0" | sed 's/^# \{0,1\}//'; exit 1; }

case "$ACTION" in
  suspend)
    cb_kubectl -n "$NS" patch cronjob "$CJ" --type merge -p '{"spec":{"suspend":true}}'
    for j in $(cb_kubectl -n "$NS" get jobs -o jsonpath='{range .items[?(@.status.active)]}{.metadata.name}{" "}{end}' | tr ' ' '\n' | grep "^$CJ" || true); do
      cb_kubectl -n "$NS" delete job "$j" --wait=true && echo "stopped $j"
    done;;
  resume) cb_kubectl -n "$NS" patch cronjob "$CJ" --type merge -p '{"spec":{"suspend":false}}';;
esac
cb_kubectl -n "$NS" get cronjob "$CJ" -o jsonpath='{.metadata.name} suspend={.spec.suspend} last={.status.lastScheduleTime}{"\n"}'
cb_kubectl -n "$NS" get jobs --no-headers 2>/dev/null | grep "^$CJ" || true
