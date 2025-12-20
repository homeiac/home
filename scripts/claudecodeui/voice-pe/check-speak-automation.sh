#!/bin/bash
# Check if speak automation triggered
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

HA_HOST="${HA_HOST:-homeassistant.maas}"

echo "=== Checking Speak Automation ==="
echo ""

echo "1. Automation state:"
curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "http://$HA_HOST:8123/api/states/automation.claude_speak_response" | jq '{state, last_triggered: .attributes.last_triggered}'

echo ""
echo "2. Testing TTS directly..."
curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
        "entity_id": "assist_satellite.home_assistant_voice_09f5a3_assist_satellite",
        "message": "Testing speech. Can you hear me?"
    }' \
    "http://$HA_HOST:8123/api/services/assist_satellite/announce" | jq '.'

echo ""
echo "If you heard speech, TTS works. If not, check Voice PE speaker."
