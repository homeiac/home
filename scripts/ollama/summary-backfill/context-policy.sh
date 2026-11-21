#!/bin/bash
# Piglet pulls only the context scheduling enum. Flux consumes the slot count
# from the same file. Queued PostgreSQL work remains durable during the hold.
set -euo pipefail
state=/var/lib/knowledge-index-summary-policy
unit=photo-enrichment-context.service
url=https://raw.githubusercontent.com/homeiac/home/master/gitops/clusters/homelab/apps/ollama/summary-backfill.env
response=$(mktemp)
trap 'rm -f "$response"' EXIT
status=$(curl --silent --show-error --max-time 20 --proto '=https' -o "$response" -w '%{http_code}' "$url")
case "$status" in
    200) policy=$(sed -n 's/^PHOTO_CONTEXT_POLICY=//p' "$response") ;;
    404) policy=shared ;;  # A Git revert can remove the policy file.
    *) echo "Policy fetch returned HTTP $status" >&2; exit 1 ;;
esac

resume_context() {
    if [[ -e "$state/paused" ]]; then
        mv "$state/paused" "$state/resuming"
    fi
    if [[ -e "$state/resuming" ]]; then
        systemctl start "$unit"
        rm -f "$state/resuming"
    fi
}

case "$policy" in
    shared) resume_context; exit 0 ;;
    after-backfill) ;;
    *) echo 'Unrecognized context policy' >&2; exit 1 ;;
esac
# Use the authoritative five-minute index export so completion survives the
# summary process exiting. A failed or stale export must not release the hold.
metrics=/var/lib/prometheus/node-exporter/knowledge_index.prom
[[ -f "$metrics" && $(( $(date +%s) - $(stat -c %Y "$metrics") )) -lt 900 ]] || exit 0
awk '$1 == "knowledge_index_exporter_success" && $2 == 1 { ok=1 } END { exit !ok }' "$metrics" || exit 0
queue=$(awk '$1 == "media_summaries_queue{enricher=\"gemma4-e2b-p1\"}" {print $2}' "$metrics")
[[ "$queue" =~ ^[0-9]+$ ]] || exit 0
if (( queue == 0 )); then
    resume_context
elif [[ -f "$state/paused" ]] || systemctl is-active --quiet "$unit"; then
    touch "$state/paused"
    systemctl stop "$unit"
fi
