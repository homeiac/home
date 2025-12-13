#!/bin/bash

# Workaround script to manually clear notification and turn off LED
# Use this if script.get_pending_notification is hung

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
    HA_URL=$(grep "^HA_URL=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

HA_URL="${HA_URL:-http://homeassistant.maas:8123}"

if [[ -z "$HA_TOKEN" ]]; then
    echo "ERROR: HA_TOKEN not found. Set it in $ENV_FILE or export HA_TOKEN"
    exit 1
fi

echo "=== Clearing Notification and LED ==="
echo

# Get current notification message
CURRENT_MESSAGE=$(curl -s -H "Authorization: Bearer $HA_TOKEN" \
  "$HA_URL/api/states/input_text.pending_notification_message" | jq -r '.state')

echo "Current notification: $CURRENT_MESSAGE"
echo

# Turn off the boolean (this will trigger the automation to turn off LED)
echo "Turning off has_pending_notification..."
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
  -d '{"entity_id": "input_boolean.has_pending_notification"}' \
  "$HA_URL/api/services/input_boolean/turn_off" > /dev/null

echo "✓ Boolean turned off"
echo

# Wait for automation to process
sleep 2

# Verify LED is off
LED_STATE=$(curl -s -H "Authorization: Bearer $HA_TOKEN" \
  "$HA_URL/api/states/light.home_assistant_voice_09f5a3_led_ring" | jq -r '.state')

if [ "$LED_STATE" == "off" ]; then
  echo "✓ LED is now OFF"
  echo "✓ Notification cleared"
else
  echo "⚠ LED is still $LED_STATE - manual intervention may be needed"
  echo "  Try: curl -X POST -H \"Authorization: Bearer $HA_TOKEN\" \\"
  echo "       -H \"Content-Type: application/json\" \\"
  echo "       -d '{\"entity_id\": \"light.home_assistant_voice_09f5a3_led_ring\"}' \\"
  echo "       \"$HA_URL/api/services/light/turn_off\""
fi

echo
echo "Done!"
