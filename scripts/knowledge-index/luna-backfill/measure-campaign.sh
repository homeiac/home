#!/usr/bin/env bash
# Read current Luna campaign totals and the 70,000-photo completion milestone.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../../backup/cloud-backup-common.sh"
cb_ssh '/usr/bin/python3 -' < "$SCRIPT_DIR/measure-campaign.py"
