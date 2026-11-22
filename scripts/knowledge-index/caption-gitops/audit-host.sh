#!/usr/bin/env bash
# Snapshot or verify committed output on the inventory-selected host.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../../backup/cloud-backup-common.sh"
case "${1:-}" in snapshot|verify) ;; *) echo 'Usage: audit-host.sh snapshot|verify' >&2; exit 2;; esac
cb_ssh "/opt/knowledge-index/venv/bin/python - $1 /var/tmp/caption-gitops-recovery-baseline.json" < "$SCRIPT_DIR/audit.py"
