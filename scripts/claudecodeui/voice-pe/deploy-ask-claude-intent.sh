#!/bin/bash
# Deploy "Ask Claude" voice intent to Home Assistant
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

HA_HOST="${HA_HOST:-homeassistant.maas}"

echo "=== Deploy Ask Claude Voice Intent ==="
echo ""

# Method 1: Deploy as automation (simpler, works with conversation trigger)
echo "1. Deploying automation..."
AUTOMATION=$(cat "$SCRIPT_DIR/automation-ask-claude-intent.yaml")

# Create automation via API
curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{
        \"id\": \"ask_claude_voice_intent\",
        \"alias\": \"Ask Claude Voice Intent\",
        \"description\": \"Route Ask Claude voice commands to Claude Code\",
        \"mode\": \"single\",
        \"trigger\": [{
            \"platform\": \"conversation\",
            \"command\": [
                \"ask claude {query}\",
                \"ask cloud {query}\",
                \"hey claude {query}\",
                \"claude {query}\"
            ]
        }],
        \"action\": [
            {
                \"service\": \"mqtt.publish\",
                \"data\": {
                    \"topic\": \"claude/command\",
                    \"payload\": \"{\\\"source\\\":\\\"voice_pe\\\",\\\"server\\\":\\\"home\\\",\\\"type\\\":\\\"chat\\\",\\\"message\\\":\\\"{{ trigger.slots.query }}\\\"}\"
                }
            },
            {
                \"set_conversation_response\": \"Asking Claude\"
            }
        ]
    }" \
    "http://$HA_HOST:8123/api/config/automation/config/ask_claude_voice_intent" | jq '.'

echo ""
echo "2. Reloading automations..."
curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    "http://$HA_HOST:8123/api/services/automation/reload" > /dev/null

echo "   Done!"
echo ""
echo "=== Test Commands ==="
echo "Say to Voice PE:"
echo "  - 'Okay Nabu, ask Claude what time is it'"
echo "  - 'Okay Nabu, claude tell me a joke'"
echo ""
echo "Or test via API:"
echo "  curl -X POST -H 'Authorization: Bearer \$HA_TOKEN' \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"text\": \"ask claude what is the weather\", \"language\": \"en\"}' \\"
echo "    'http://$HA_HOST:8123/api/conversation/process'"
