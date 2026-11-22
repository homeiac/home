#!/usr/bin/env bash
# Confirm exact successful output counts for the recovery cohort, without paths.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../backup/cloud-backup-common.sh"
cb_ssh '/opt/knowledge-index/venv/bin/python -' < "$SCRIPT_DIR/verify-caption-gaps.py"
