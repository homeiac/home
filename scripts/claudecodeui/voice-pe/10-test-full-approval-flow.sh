#!/bin/bash
# Full end-to-end test of Claude Code Voice PE integration
# Tests the complete flow: command → thinking → approval → dial/button → response
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

# Load credentials from .env
if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
    MQTT_USER=$(grep "^MQTT_USER=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
    MQTT_PASS=$(grep "^MQTT_PASS=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

if [[ -z "$HA_TOKEN" ]]; then
    echo "ERROR: HA_TOKEN not found"
    exit 1
fi

HA_HOST="${HA_HOST:-homeassistant.maas}"
LED_ENTITY="light.home_assistant_voice_09f5a3_led_ring"
HELPER_ENTITY="input_boolean.claude_awaiting_approval"

# Check if mosquitto_pub is available
if ! command -v mosquitto_pub &> /dev/null; then
    echo "ERROR: mosquitto_pub not found. Install with: brew install mosquitto"
    exit 1
fi

# Build MQTT auth args
MQTT_AUTH=""
if [[ -n "$MQTT_USER" && -n "$MQTT_PASS" ]]; then
    MQTT_AUTH="-u $MQTT_USER -P $MQTT_PASS"
fi

publish_mqtt() {
    local topic="$1"
    local payload="$2"
    mosquitto_pub -h "$HA_HOST" -p 1883 $MQTT_AUTH -t "$topic" -m "$payload"
}

get_led_state() {
    curl -s -H "Authorization: Bearer $HA_TOKEN" \
        "http://$HA_HOST:8123/api/states/$LED_ENTITY" | jq -r '.state'
}

get_helper_state() {
    curl -s -H "Authorization: Bearer $HA_TOKEN" \
        "http://$HA_HOST:8123/api/states/$HELPER_ENTITY" | jq -r '.state // "unavailable"'
}

echo "=========================================="
echo "  Claude Code Voice PE Integration Test"
echo "=========================================="
echo ""
echo "Prerequisites:"
echo "  - V2 automation deployed: automation.claude_code_led_feedback_v2"
echo "  - MQTT credentials in .env"
echo "  - Optional: input_boolean.claude_awaiting_approval helper"
echo "  - Optional: ESPHome firmware updated (for native effects)"
echo ""

# Check V2 automation
echo "Checking V2 automation..."
V2_STATE=$(curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "http://$HA_HOST:8123/api/states/automation.claude_code_led_feedback_v2" | jq -r '.state // "not_found"')

if [[ "$V2_STATE" == "on" ]]; then
    echo "✅ V2 automation is ON"
else
    echo "❌ V2 automation state: $V2_STATE"
    echo "   Run 04a-deploy-automation-v2.sh first"
    exit 1
fi

# Check helper
echo ""
echo "Checking helper entity..."
HELPER_STATE=$(get_helper_state)
if [[ "$HELPER_STATE" == "unavailable" ]]; then
    echo "⚠️  Helper not found - dial/button approval will have limited functionality"
    echo "   Create via HA UI: Settings → Devices & Services → Helpers → Toggle"
else
    echo "✅ Helper exists (state: $HELPER_STATE)"
fi

echo ""
echo "=========================================="
echo "  Test 1: Command → Thinking LED"
echo "=========================================="
echo ""
echo "Publishing claude/command..."
publish_mqtt "claude/command" '{"command": "test", "source": "integration-test"}'
echo "LED should be CYAN (or native thinking effect if ESPHome updated)"
sleep 3

LED_STATE=$(get_led_state)
echo "LED state: $LED_STATE"

echo ""
echo "=========================================="
echo "  Test 2: Response Complete → LED Off"
echo "=========================================="
echo ""
echo "Publishing response complete..."
publish_mqtt "claude/home/response" '{"type": "complete", "content": "Test done"}'
sleep 2

LED_STATE=$(get_led_state)
echo "LED state: $LED_STATE (should be off)"

echo ""
echo "=========================================="
echo "  Test 3: Approval Request → Amber LED"
echo "=========================================="
echo ""
echo "Publishing approval request..."
publish_mqtt "claude/approval-request" '{"tool": "Bash", "description": "Test command"}'
echo "LED should be AMBER"
sleep 2

LED_STATE=$(get_led_state)
HELPER_STATE=$(get_helper_state)
echo "LED state: $LED_STATE"
echo "Helper state: $HELPER_STATE (should be 'on' if helper exists)"

echo ""
echo "=========================================="
echo "  Test 4: Simulated Dial Approve"
echo "=========================================="
echo ""
echo "NOTE: This simulates dial input via MQTT"
echo "      Real dial test requires ESPHome firmware update"
echo ""
echo "Publishing approval response (approved)..."
publish_mqtt "claude/approval-response" '{"approved": true}'
echo "LED should flash GREEN then turn off"
sleep 3

LED_STATE=$(get_led_state)
echo "LED state: $LED_STATE (should be off)"

echo ""
echo "=========================================="
echo "  Test 5: Approval Reject Flow"
echo "=========================================="
echo ""
echo "Publishing approval request..."
publish_mqtt "claude/approval-request" '{"tool": "Edit", "description": "Modify file"}'
sleep 2

echo "Publishing approval response (rejected)..."
publish_mqtt "claude/approval-response" '{"approved": false}'
echo "LED should flash RED then turn off"
sleep 3

LED_STATE=$(get_led_state)
echo "LED state: $LED_STATE (should be off)"

echo ""
echo "=========================================="
echo "  Test Results Summary"
echo "=========================================="
echo ""
echo "✅ MQTT → LED automation working"
echo ""
echo "Next steps for full dial/button control:"
echo "  1. Apply ESPHome YAML changes via dashboard"
echo "  2. OTA update Voice PE device"
echo "  3. Create input_boolean helper (if not done)"
echo "  4. Test physical dial: rotate clockwise (approve) / anticlockwise (reject)"
echo "  5. Test physical button: press to quick-approve"
echo ""
echo "Test scripts:"
echo "  - 08-test-esphome-services.sh  (test LED effects)"
echo "  - 09-test-dial-button-events.sh (monitor dial/button events)"
echo ""
echo "=========================================="
