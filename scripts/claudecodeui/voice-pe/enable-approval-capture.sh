#!/bin/bash
# Re-enable the approval capture automation (has voice prompt)
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

[[ -f "$ENV_FILE" ]] && HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
[[ -z "$HA_TOKEN" ]] && { echo "ERROR: HA_TOKEN not found"; exit 1; }

HA_HOST="${HA_HOST:-homeassistant.maas:8123}"

echo "Enabling automation.claude_approval_capture_request..."
curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"entity_id": "automation.claude_approval_capture_request"}' \
    "http://$HA_HOST/api/services/automation/turn_on"

echo ""
/Users/10381054/code/home/scripts/haos/list-automations.sh claude
