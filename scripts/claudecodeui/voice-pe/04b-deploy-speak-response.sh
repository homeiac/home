#!/bin/bash
# Deploy Claude Speak Response automation to Home Assistant
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"
AUTOMATION_FILE="$SCRIPT_DIR/automation-speak-response.yaml"

if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

if [[ -z "$HA_TOKEN" ]]; then
    echo "ERROR: HA_TOKEN not found"
    exit 1
fi

HA_HOST="${HA_HOST:-homeassistant.maas}"

echo "=== Deploying Claude Speak Response Automation ==="
echo "Target: $HA_HOST"
echo ""

# Convert YAML to JSON
AUTOMATION_JSON=$(python3 -c "
import yaml
import json

with open('$AUTOMATION_FILE', 'r') as f:
    data = yaml.safe_load(f)

output = {
    'id': 'claude_speak_response',
    'alias': data.get('alias', 'Claude Speak Response'),
    'description': data.get('description', ''),
    'mode': data.get('mode', 'queued'),
    'max': data.get('max', 5),
    'trigger': data.get('trigger', []),
    'condition': data.get('condition', []),
    'action': data.get('action', [])
}
print(json.dumps(output))
")

echo "Creating automation..."
RESULT=$(curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d "$AUTOMATION_JSON" \
    "http://$HA_HOST:8123/api/config/automation/config/claude_speak_response")

echo "API Response: $RESULT"

echo ""
echo "Reloading automations..."
curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -d '{}' \
    "http://$HA_HOST:8123/api/services/automation/reload" > /dev/null

sleep 2

echo ""
echo "Verifying..."
curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "http://$HA_HOST:8123/api/states/automation.claude_speak_response" | jq '{entity_id, state}'

echo ""
echo "=== Done ==="
