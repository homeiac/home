#!/bin/bash
# Deploy voice approval intents to HA
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

[[ -f "$ENV_FILE" ]] && HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
[[ -z "$HA_TOKEN" ]] && { echo "ERROR: HA_TOKEN not found"; exit 1; }

HA_HOST="${HA_HOST:-homeassistant.maas}"
HA_URL="http://${HA_HOST}:8123"

echo "=== Deploying voice approval intents ==="

# Check if input_boolean.claude_awaiting_approval exists
echo "Checking for input_boolean.claude_awaiting_approval..."
STATE=$(curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/states/input_boolean.claude_awaiting_approval" | jq -r '.state // "not_found"')
if [[ "$STATE" == "not_found" ]]; then
    echo "WARNING: input_boolean.claude_awaiting_approval not found!"
    echo "Create it in HA: Settings > Devices > Helpers > Toggle"
    echo ""
fi

echo ""
echo "=== Files to deploy ==="
echo "1. custom_sentences/en/voice_approval.yaml -> /config/custom_sentences/en/"
echo "2. intent_scripts/voice_approval.yaml -> merge into /config/intent_script.yaml"
echo ""
echo "=== Manual steps ==="
echo "1. SSH to HA or use File Editor addon"
echo "2. Create /config/custom_sentences/en/ if not exists"
echo "3. Copy voice_approval.yaml to custom_sentences/en/"
echo "4. Merge intent_scripts/voice_approval.yaml into /config/intent_script.yaml"
echo "5. Restart HA or reload intents"
echo ""
echo "=== Testing ==="
echo "1. Turn on input_boolean.claude_awaiting_approval"
echo "2. Say 'Hey Nabu, yes' - should hear 'Approved'"
echo "3. Say 'Hey Nabu, no' - should hear 'Rejected'"
echo "4. With boolean off, should hear 'Nothing pending'"
