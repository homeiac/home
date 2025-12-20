#!/bin/bash
# Get Wyoming/Piper config entry details
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

HA_HOST="${HA_HOST:-homeassistant.maas}"

echo "=== Wyoming Config Entries ==="

# Get all config entries and filter for wyoming
curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "http://$HA_HOST:8123/api/config/config_entries/entry" | \
    jq '.[] | select(.domain == "wyoming")'

echo ""
echo "=== Select entities for TTS ==="
curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "http://$HA_HOST:8123/api/states" | \
    jq -r '.[] | select(.entity_id | startswith("select.") and test("piper|voice|tts")) | "\(.entity_id): \(.state)"'
