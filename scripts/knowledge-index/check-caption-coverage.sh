#!/usr/bin/env bash
# Read-only union coverage audit; set CB_HOST from proxmox/inventory.txt.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../backup/cloud-backup-common.sh"
cb_ssh '/opt/knowledge-index/venv/bin/python -' < "$SCRIPT_DIR/check-caption-coverage.py"
