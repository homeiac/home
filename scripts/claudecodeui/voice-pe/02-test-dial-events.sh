#!/bin/bash
# Listen for dial events from Voice PE
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

[[ -z "$HA_TOKEN" ]] && { echo "ERROR: HA_TOKEN not found"; exit 1; }

echo "=== Listening for Voice PE Dial Events ==="
echo "Rotate the dial clockwise or counter-clockwise..."
echo ""
echo "Checking HA event history for esphome.voice_pe_dial..."
echo ""

# Check recent events via logbook
curl -s --max-time 10 -H "Authorization: Bearer $HA_TOKEN" \
    "http://192.168.1.122:8123/api/events" 2>/dev/null | \
    jq -r '.[] | select(.event_type == "esphome.voice_pe_dial")' 2>/dev/null || echo "No events found yet"

echo ""
echo "Tip: Open HA Developer Tools → Events → Listen to 'esphome.voice_pe_dial'"
