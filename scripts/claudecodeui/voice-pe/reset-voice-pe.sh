#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"
HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
HA_HOST="${HA_HOST:-homeassistant.maas}"

echo "=== Resetting Voice PE ==="

echo "1. Turning off LED..."
curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"entity_id": "light.home_assistant_voice_09f5a3_led_ring"}' \
    "http://$HA_HOST:8123/api/services/light/turn_off" > /dev/null

echo "2. Checking satellite state..."
STATE=$(curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "http://$HA_HOST:8123/api/states/assist_satellite.home_assistant_voice_09f5a3_assist_satellite" | jq -r '.state')
echo "   Current state: $STATE"

if [[ "$STATE" == "responding" ]]; then
    echo "3. Satellite stuck in responding - may need physical reset or wait"
fi

echo ""
echo "Done. If still stuck, try saying wake word to Voice PE to reset it."
