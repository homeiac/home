#!/bin/bash
# List all Home Assistant integrations via API

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ENV_FILE="$SCRIPT_DIR/../../proxmox/homelab/.env"
[[ -f "$ENV_FILE" ]] && HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
[[ -z "$HA_TOKEN" ]] && { echo "ERROR: HA_TOKEN not found"; exit 1; }

HA_URL="${HA_URL:-http://192.168.4.240:8123}"

echo "Fetching integrations from $HA_URL..."
curl -s --max-time 10 -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/config/config_entries/entry" | jq -r '.[] | "\(.domain): \(.title)"' | sort
