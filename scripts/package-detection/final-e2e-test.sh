#!/bin/bash
# Final E2E Test - Voice Notification System

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

HA_URL="${HA_URL:-http://192.168.4.240:8123}"

if [[ -z "$HA_TOKEN" ]]; then
    echo "ERROR: HA_TOKEN not found in $ENV_FILE"
    exit 1
fi

echo "=== FINAL E2E TEST ==="
echo ""

# Setup
TEST_VALUE="FINAL-E2E-$(date +%s)"
echo "1. Setup: $TEST_VALUE"
curl -s --max-time 10 -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    -d "{\"entity_id\": \"input_text.pending_notification_message\", \"value\": \"$TEST_VALUE\"}" \
    "$HA_URL/api/services/input_text/set_value" > /dev/null
curl -s --max-time 10 -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    -d '{"entity_id": "input_boolean.has_pending_notification"}' \
    "$HA_URL/api/services/input_boolean/turn_on" > /dev/null
curl -s --max-time 10 -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    -d '{"entity_id": "light.home_assistant_voice_09f5a3_led_ring", "rgb_color": [0, 0, 255], "brightness": 128}' \
    "$HA_URL/api/services/light/turn_on" > /dev/null
sleep 2

# Check initial
echo ""
echo "2. Initial state:"
BOOL=$(curl -s --max-time 5 -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/states/input_boolean.has_pending_notification" | jq -r '.state')
LED=$(curl -s --max-time 5 -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/states/light.home_assistant_voice_09f5a3_led_ring" | jq -r '.state')
MSG=$(curl -s --max-time 5 -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/states/input_text.pending_notification_message" | jq -r '.state')
echo "   Message: $MSG"
echo "   Boolean: $BOOL"
echo "   LED: $LED"

# Voice query
echo ""
echo "3. Voice query: 'what is my notification'"
RESP=$(curl -s --max-time 30 -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    -d '{"text": "what is my notification", "language": "en"}' \
    "$HA_URL/api/conversation/process")
echo "   Response: $(echo "$RESP" | jq -r '.response.speech.plain.speech')"

# Wait for TTS
echo ""
echo "4. Waiting 15 seconds for TTS and script actions..."
sleep 15

# Final state
echo ""
echo "5. Final state:"
FINAL_BOOL=$(curl -s --max-time 5 -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/states/input_boolean.has_pending_notification" | jq -r '.state')
FINAL_LED=$(curl -s --max-time 5 -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/states/light.home_assistant_voice_09f5a3_led_ring" | jq -r '.state')
echo "   Boolean: $FINAL_BOOL (expected: off)"
echo "   LED: $FINAL_LED (expected: off)"

# Result
echo ""
echo "=== RESULT ==="
if [[ "$FINAL_BOOL" == "off" ]] && [[ "$FINAL_LED" == "off" ]]; then
    echo "✓✓✓ ALL TESTS PASSED! ✓✓✓"
    echo ""
    echo "Voice notification system is WORKING!"
    echo ""
    echo "WORKING COMMANDS:"
    echo "  - 'what is my notification'"
    echo "  - 'what's my notification'"
    echo "  - 'check notifications'"
    echo "  - 'do I have notifications'"
    echo "  - 'read my notification'"
    echo ""
    echo "KNOWN LIMITATION:"
    echo "  - 'what is THE notification' does NOT work"
    echo "  - Use 'my' instead of 'the'"
    exit 0
else
    echo "✗ TEST FAILED"
    exit 1
fi
