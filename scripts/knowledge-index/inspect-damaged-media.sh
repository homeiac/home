#!/usr/bin/env bash
# Inspect malformed media and mounted recovery sources, without changing files.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../backup/cloud-backup-common.sh"
cb_ssh '/opt/knowledge-index/venv/bin/python -' < "$SCRIPT_DIR/inspect-damaged-media.py"
