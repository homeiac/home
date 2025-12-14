#!/bin/bash
# Reload Frigate integration in Home Assistant
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

[[ -z "$HA_TOKEN" ]] && { echo "ERROR: HA_TOKEN not found"; exit 1; }

HA_URL="${HA_URL:-http://192.168.4.240:8123}"

# Get Frigate entry_id from config
echo "Finding Frigate integration entry_id..."
ENTRY_ID=$(curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/config/config_entries/entry" | \
    jq -r '.[] | select(.domain == "frigate") | .entry_id')

if [[ -z "$ENTRY_ID" || "$ENTRY_ID" == "null" ]]; then
    echo "ERROR: Could not find Frigate integration"
    exit 1
fi

echo "Found Frigate entry_id: $ENTRY_ID"
echo "Reloading Frigate integration..."

RESULT=$(curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    "$HA_URL/api/config/config_entries/entry/$ENTRY_ID/reload")

echo "Result: $RESULT"
echo ""
echo "Waiting 5s for entities to register..."
sleep 5

# Check if entities appeared
ENTITY_COUNT=$(curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/states" | \
    jq '[.[] | select(.entity_id | startswith("camera.") and contains("frigate"))] | length')

echo "Frigate camera entities found: $ENTITY_COUNT"
