#!/bin/bash
# Reset the Voice PE satellite and LED ring
# Usage: reset-voice-pe.sh [message]
#
# The Voice PE can get stuck in two independent ways:
# 1. assist_satellite entity stuck in non-idle state (HA-side)
# 2. LED ring stuck on (ESP32-side voice_assistant_phase not reset)
#
# This script fixes both: announces to cycle satellite state,
# then explicitly turns off the LED ring.

source "$(dirname "$0")/../lib-sh/ha-api.sh"

MESSAGE="${1:-System reset}"
SAT_ENTITY="assist_satellite.home_assistant_voice_09f5a3_assist_satellite"
LED_ENTITY="light.home_assistant_voice_09f5a3_led_ring"

# 1. Check current state
SAT_STATE=$(ha_get_state "$SAT_ENTITY" | jq -r '.state' 2>/dev/null)
LED_STATE=$(ha_get_state "$LED_ENTITY" | jq -r '.state' 2>/dev/null)
echo "Current: satellite=$SAT_STATE, led_ring=$LED_STATE"

# 2. Send announce to cycle satellite state
echo "Sending announce: '$MESSAGE'"
RESULT=$(curl -s --fail-with-body --max-time 30 \
    -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    --data-raw "{\"entity_id\": \"$SAT_ENTITY\", \"message\": \"$MESSAGE\"}" \
    "$HA_URL/api/services/assist_satellite/announce")

STATE=$(echo "$RESULT" | jq -r '.[0].state' 2>/dev/null)
echo "Satellite state: $STATE"

# 3. Wait for announce to complete, then force LED off
# The announce cycles: idle → responding → idle
# But the LED ring is independent (ESP32-side) and may not turn off
sleep 3

curl -s --fail-with-body --max-time 10 \
    -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    --data-raw "{\"entity_id\": \"$LED_ENTITY\"}" \
    "$HA_URL/api/services/light/turn_off" >/dev/null 2>&1

# 4. Verify final state
SAT_STATE=$(ha_get_state "$SAT_ENTITY" | jq -r '.state' 2>/dev/null)
LED_STATE=$(ha_get_state "$LED_ENTITY" | jq -r '.state' 2>/dev/null)
echo "Final: satellite=$SAT_STATE, led_ring=$LED_STATE"
