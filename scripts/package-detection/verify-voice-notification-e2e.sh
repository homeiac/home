#!/bin/bash
# E2E Verification: Voice PE Notification System
# Tests the complete flow from notification to voice query to LED off

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

echo "========================================================"
echo "  E2E Verification: Voice PE Notification System"
echo "========================================================"
echo ""
echo "This test verifies the complete flow:"
echo "1. Set notification state and turn on LED"
echo "2. Ask 'what is my notification' via voice"
echo "3. Script runs, announces message, clears state, turns off LED"
echo ""

# Test value for verification
TEST_VALUE="E2E-TEST-$(date +%s)"
PASS_COUNT=0
FAIL_COUNT=0

test_result() {
    local test_name="$1"
    local expected="$2"
    local actual="$3"

    if [[ "$expected" == "$actual" ]]; then
        echo "  ✓ PASS: $test_name"
        ((PASS_COUNT++))
    else
        echo "  ✗ FAIL: $test_name"
        echo "    Expected: $expected"
        echo "    Actual:   $actual"
        ((FAIL_COUNT++))
    fi
}

echo "========================================================"
echo "  Step 1: Setup - Set Notification State"
echo "========================================================"
echo ""

echo "Setting notification message: $TEST_VALUE"
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    -d "{\"entity_id\": \"input_text.pending_notification_message\", \"value\": \"$TEST_VALUE\"}" \
    "$HA_URL/api/services/input_text/set_value" > /dev/null

echo "Turning on has_pending_notification..."
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    -d '{"entity_id": "input_boolean.has_pending_notification"}' \
    "$HA_URL/api/services/input_boolean/turn_on" > /dev/null

echo "Turning on LED (blue)..."
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    -d '{"entity_id": "light.home_assistant_voice_09f5a3_led_ring", "rgb_color": [0, 0, 255], "brightness": 128}' \
    "$HA_URL/api/services/light/turn_on" > /dev/null

sleep 2

echo ""
echo "Verifying initial state..."
MSG_STATE=$(curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/states/input_text.pending_notification_message" | jq -r '.state')
BOOL_STATE=$(curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/states/input_boolean.has_pending_notification" | jq -r '.state')
LED_STATE=$(curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/states/light.home_assistant_voice_09f5a3_led_ring" | jq -r '.state')

test_result "Notification message set" "$TEST_VALUE" "$MSG_STATE"
test_result "Boolean flag on" "on" "$BOOL_STATE"
test_result "LED is on" "on" "$LED_STATE"

echo ""
echo "========================================================"
echo "  Step 2: Voice Query - 'what is my notification'"
echo "========================================================"
echo ""

BEFORE_TRIGGERED=$(curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/states/script.get_pending_notification" | jq -r '.attributes.last_triggered // "never"')

echo "Sending voice query: 'what is my notification'..."
RESPONSE=$(curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    -d '{"text": "what is my notification", "language": "en"}' \
    "$HA_URL/api/conversation/process")

SPEECH=$(echo "$RESPONSE" | jq -r '.response.speech.plain.speech // "N/A"')
RESP_TYPE=$(echo "$RESPONSE" | jq -r '.response.response_type // "N/A"')

echo "Response type: $RESP_TYPE"
echo "Response speech: $SPEECH"

AFTER_TRIGGERED=$(curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/states/script.get_pending_notification" | jq -r '.attributes.last_triggered // "never"')

if [[ "$BEFORE_TRIGGERED" != "$AFTER_TRIGGERED" ]]; then
    echo ""
    test_result "Script triggered" "triggered" "triggered"
else
    echo ""
    test_result "Script triggered" "triggered" "NOT triggered"
fi

echo ""
echo "========================================================"
echo "  Step 3: Verify Final State"
echo "========================================================"
echo ""

# Wait for script to complete its actions (TTS announcement takes time)
echo "Waiting 15 seconds for script to complete (includes TTS)..."
sleep 15

FINAL_BOOL=$(curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/states/input_boolean.has_pending_notification" | jq -r '.state')
FINAL_LED=$(curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/states/light.home_assistant_voice_09f5a3_led_ring" | jq -r '.state')

test_result "Boolean flag off" "off" "$FINAL_BOOL"
test_result "LED is off" "off" "$FINAL_LED"

echo ""
echo "========================================================"
echo "  RESULTS SUMMARY"
echo "========================================================"
echo ""
echo "  PASSED: $PASS_COUNT"
echo "  FAILED: $FAIL_COUNT"
echo ""

if [[ $FAIL_COUNT -eq 0 ]]; then
    echo "  ✓✓✓ ALL TESTS PASSED! ✓✓✓"
    echo ""
    echo "  Voice notification system is working correctly."
    echo ""
    echo "  WORKING PHRASINGS:"
    echo "    - 'what is my notification'"
    echo "    - 'what's my notification'"
    echo "    - 'check notifications'"
    echo "    - 'do I have notifications'"
    echo "    - 'read my notification'"
    echo ""
    echo "  KNOWN LIMITATION:"
    echo "    - 'what is THE notification' does NOT work"
    echo "    - Use 'my' instead of 'the'"
    echo ""
    exit 0
else
    echo "  ✗✗✗ SOME TESTS FAILED! ✗✗✗"
    echo ""
    echo "  Review the failed tests above and investigate."
    echo ""
    exit 1
fi
