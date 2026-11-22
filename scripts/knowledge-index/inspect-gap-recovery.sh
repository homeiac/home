#!/usr/bin/env bash
# Read-only deeper source inspection for caption recovery.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../backup/cloud-backup-common.sh"
cb_ssh '/opt/knowledge-index/venv/bin/python -' < "$SCRIPT_DIR/inspect-gap-recovery.py"
