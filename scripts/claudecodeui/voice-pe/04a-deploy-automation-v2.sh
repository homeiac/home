#!/bin/bash
# Deploy Claude Code LED V2 automation to Home Assistant
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"
AUTOMATION_FILE="$SCRIPT_DIR/automation-claude-led-v2.yaml"

# Load HA_TOKEN from .env
if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

if [[ -z "$HA_TOKEN" ]]; then
    echo "ERROR: HA_TOKEN not found in $ENV_FILE"
    exit 1
fi

HA_HOST="${HA_HOST:-homeassistant.maas}"
AUTOMATION_ID="automation.claude_code_led_feedback_v2"

echo "=== Deploying Claude Code LED V2 Automation ==="
echo "Target: $HA_HOST"
echo "Automation file: $AUTOMATION_FILE"
echo ""

# Check if automation exists
echo "Checking if automation exists..."
EXISTING=$(curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "http://$HA_HOST:8123/api/states/$AUTOMATION_ID" | jq -r '.state // "not_found"')

if [[ "$EXISTING" != "not_found" && "$EXISTING" != "null" ]]; then
    echo "Automation exists (state: $EXISTING), will update..."
else
    echo "Automation not found, will create..."
fi

# Convert YAML to JSON for the API
echo ""
echo "Converting YAML to JSON..."
AUTOMATION_JSON=$(python3 -c "
import yaml
import json
import sys

with open('$AUTOMATION_FILE', 'r') as f:
    data = yaml.safe_load(f)

# Wrap for creation API
output = {
    'id': 'claude_code_led_feedback_v2',
    'alias': data.get('alias', 'Claude Code LED Feedback V2'),
    'description': data.get('description', ''),
    'mode': data.get('mode', 'restart'),
    'trigger': data.get('trigger', []),
    'condition': data.get('condition', []),
    'action': data.get('action', [])
}
print(json.dumps(output))
")

if [[ -z "$AUTOMATION_JSON" ]]; then
    echo "ERROR: Failed to convert YAML to JSON"
    exit 1
fi

echo "JSON prepared ($(echo "$AUTOMATION_JSON" | wc -c) bytes)"

# Create/Update the automation using config entry approach
echo ""
echo "Creating automation via HA API..."

RESULT=$(curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d "$AUTOMATION_JSON" \
    "http://$HA_HOST:8123/api/config/automation/config/claude_code_led_feedback_v2")

echo "API Response: $RESULT"

# Reload automations
echo ""
echo "Reloading automations..."
curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{}' \
    "http://$HA_HOST:8123/api/services/automation/reload" | jq '.'

# Wait for reload
sleep 2

# Verify
echo ""
echo "Verifying automation state..."
curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "http://$HA_HOST:8123/api/states/$AUTOMATION_ID" | jq '{entity_id, state, last_changed}'

echo ""
echo "=== V2 Deployment Complete ==="
echo ""
echo "Note: V1 automation remains active. To test V2:"
echo "  1. Disable V1: scripts/claudecodeui/voice-pe/disable-v1.sh"
echo "  2. Test V2 with MQTT commands"
echo "  3. Re-enable V1 if needed: scripts/claudecodeui/voice-pe/enable-v1.sh"
echo ""
