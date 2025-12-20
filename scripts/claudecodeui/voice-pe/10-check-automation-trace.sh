#!/bin/bash
# Check automation trace for speak response
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

HA_URL="http://192.168.1.122:8123"

echo "=== Automation Trace ==="
curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/trace/automation/claude_speak_response" 2>/dev/null | jq '.[0] | {run_id, state, timestamp, trigger: .trigger}' 2>/dev/null || echo "No traces or automation not found"

echo ""
echo "Last triggered:"
curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/states/automation.claude_speak_response" | jq '.attributes.last_triggered'
