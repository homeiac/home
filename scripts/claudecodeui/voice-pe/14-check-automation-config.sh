#!/bin/bash
# Check the dial CW automation config
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

HA_URL="http://192.168.1.122:8123"

echo "=== Dial CW Automation Config ==="
curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/config/automation/config/claude_approval_dial_cw" | jq '.action[] | select(.service == "mqtt.publish")'
