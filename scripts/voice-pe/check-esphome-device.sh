#!/bin/bash
# Check ESPHome device info in HA device registry
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../proxmox/homelab/.env"

[[ -f "$ENV_FILE" ]] && HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
[[ -z "$HA_TOKEN" ]] && { echo "ERROR: HA_TOKEN not found"; exit 1; }

HA_URL="${HA_URL:-http://192.168.1.122:8123}"

echo "=== ESPHome Device Registry ==="
# Get via websocket API - need to use template
curl -s -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"template": "{{ states.switch | selectattr(\"entity_id\", \"search\", \"09f5a3\") | map(attribute=\"entity_id\") | list }}"}' \
    "$HA_URL/api/template"

echo ""
echo "=== Device diagnostics ==="
# Check the integration diagnostics
curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/diagnostics/config_entry/01KBR6935BVYK5EX7PF6D4QYEY" 2>/dev/null | jq '.data.device_info // .data // "no diagnostics"' 2>/dev/null || echo "Diagnostics not available"
