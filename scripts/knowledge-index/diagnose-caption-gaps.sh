#!/usr/bin/env bash
# Diagnose remaining caption gaps on the inventory-selected host; no inference.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../backup/cloud-backup-common.sh"
cb_ssh '/opt/knowledge-index/venv/bin/python -' < "$SCRIPT_DIR/diagnose-caption-gaps.py"
