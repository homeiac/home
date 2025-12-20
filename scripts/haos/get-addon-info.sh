#!/bin/bash
# Get HA addon info
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../proxmox/homelab/.env"

[[ -f "$ENV_FILE" ]] && HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
[[ -z "$HA_TOKEN" ]] && { echo "ERROR: HA_TOKEN not found"; exit 1; }

HA_URL="${HA_URL:-http://192.168.1.122:8123}"
ADDON="${1:?Usage: $0 <addon_slug>}"

RESPONSE=$(curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/hassio/addons/$ADDON/info")
echo "$RESPONSE" | jq '{state: .data.state, version: .data.version, name: .data.name}' 2>/dev/null || echo "$RESPONSE"
