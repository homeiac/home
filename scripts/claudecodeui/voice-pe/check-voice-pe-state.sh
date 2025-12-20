#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"
HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
HA_HOST="${HA_HOST:-homeassistant.maas}"

echo "=== Voice PE State ==="
echo ""
echo "Assist Satellite:"
curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "http://$HA_HOST:8123/api/states/assist_satellite.home_assistant_voice_09f5a3_assist_satellite" | jq '{state, last_changed}'

echo ""
echo "LED Ring:"
curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "http://$HA_HOST:8123/api/states/light.home_assistant_voice_09f5a3_led_ring" | jq '{state, last_changed}'

echo ""
echo "Speak Automation:"
curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "http://$HA_HOST:8123/api/states/automation.claude_speak_response" | jq '{state, last_triggered: .attributes.last_triggered, current: .attributes.current}'
