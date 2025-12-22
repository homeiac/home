#!/bin/bash
# Check ESPHome config entries in HA
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../proxmox/homelab/.env"

[[ -f "$ENV_FILE" ]] && HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
[[ -z "$HA_TOKEN" ]] && { echo "ERROR: HA_TOKEN not found"; exit 1; }

HA_URL="${HA_URL:-http://192.168.1.122:8123}"

echo "=== ESPHome Config Entries ==="
curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/config/config_entries/entry" | \
    jq '.[] | select(.domain == "esphome") | {title, state, entry_id, data}'
