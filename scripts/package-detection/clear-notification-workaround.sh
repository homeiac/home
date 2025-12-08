#!/bin/bash

# Workaround script to manually clear notification and turn off LED
# Use this if script.get_pending_notification is hung

set -e

HA_URL="http://192.168.4.240:8123"
HA_TOKEN="REDACTED_HA_TOKEN"

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
