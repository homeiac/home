#!/bin/bash
# Get Voice PE LED ring attributes including available effects
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

# Load HA_TOKEN from .env
if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

if [[ -z "$HA_TOKEN" ]]; then
    echo "ERROR: HA_TOKEN not found"
    exit 1
fi

HA_HOST="${HA_HOST:-homeassistant.maas}"
LED_ENTITY="${1:-light.home_assistant_voice_09f5a3_led_ring}"

echo "=== Voice PE LED Ring Attributes ==="
echo "Entity: $LED_ENTITY"
echo ""

curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "http://$HA_HOST:8123/api/states/$LED_ENTITY" | jq '.'

echo ""
echo "--- Available Effects ---"
curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "http://$HA_HOST:8123/api/states/$LED_ENTITY" | \
    jq -r '.attributes.effect_list // ["No effects exposed"] | .[]'
