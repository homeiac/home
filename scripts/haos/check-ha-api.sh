#!/bin/bash
# Check if Home Assistant API is responding
# HAOS has NO SSH - use API or qm guest exec

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load HA_TOKEN from .env
ENV_FILE="$SCRIPT_DIR/../../proxmox/homelab/.env"
[[ -f "$ENV_FILE" ]] && HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
[[ -z "$HA_TOKEN" ]] && { echo "ERROR: HA_TOKEN not found in $ENV_FILE"; exit 1; }

HA_URL="${HA_URL:-http://192.168.4.240:8123}"

echo "Checking Home Assistant API at $HA_URL..."
curl -s --max-time 10 -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/" | jq .
