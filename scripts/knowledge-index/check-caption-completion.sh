#!/usr/bin/env bash
# Show the host's copy-aware coverage snapshot; optionally refresh the exporter.
# CB_HOST must come from proxmox/inventory.txt. No media paths are printed.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../backup/cloud-backup-common.sh"
case "${1:-}" in
  --refresh) cb_ssh 'systemctl start knowledge-index-metrics.service' ;;
  '') ;;
  *) echo 'Usage: check-caption-completion.sh [--refresh]' >&2; exit 2 ;;
esac
cb_ssh 'grep -E "^(knowledge_index_caption_completion|knowledge_index_exporter_success|knowledge_index_last_run_timestamp_seconds) " /var/lib/prometheus/node-exporter/knowledge_index.prom; grep -E "^knowledge_index_caption_completion\\{" /var/lib/prometheus/node-exporter/knowledge_index.prom'
