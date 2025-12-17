#!/bin/bash
# Diagnose why approval-request isn't being processed
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

[[ -f "$ENV_FILE" ]] && HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
[[ -z "$HA_TOKEN" ]] && { echo "ERROR: HA_TOKEN not found"; exit 1; }

# Also load MQTT creds from claudecodeui .env
CCUI_ENV="/Users/10381054/code/claudecodeui/.env"
if [[ -f "$CCUI_ENV" ]]; then
    export $(grep -v '^#' "$CCUI_ENV" | xargs)
fi
MQTT_HOST="${MQTT_BROKER_URL#mqtt://}"
MQTT_HOST="${MQTT_HOST%:*}"
MQTT_HOST="${MQTT_HOST:-homeassistant.maas}"
MQTT_USER="${MQTT_USERNAME:-}"
MQTT_PASS="${MQTT_PASSWORD:-}"

HA_HOST="${HA_HOST:-homeassistant.maas:8123}"

echo "=== APPROVAL FLOW DIAGNOSIS ==="
echo ""

# Step 1: Current state
echo "1. CURRENT STATE"
echo "   input_text.claude_approval_request_id:"
CURRENT_ID=$(curl -s -H "Authorization: Bearer $HA_TOKEN" "http://$HA_HOST/api/states/input_text.claude_approval_request_id" | jq -r '.state')
echo "   -> $CURRENT_ID"
echo ""

# Step 2: Test MQTT publish to approval-request
TEST_ID="test-$(date +%s)"
echo "2. PUBLISHING TEST APPROVAL-REQUEST"
echo "   Test requestId: $TEST_ID"
echo "   Topic: claude/approval-request"

if [[ -n "$MQTT_USER" && -n "$MQTT_PASS" ]]; then
    mosquitto_pub -h "$MQTT_HOST" -u "$MQTT_USER" -P "$MQTT_PASS" \
        -t "claude/approval-request" \
        -m "{\"requestId\":\"$TEST_ID\",\"toolName\":\"TestTool\",\"input\":{\"command\":\"test\"},\"sessionId\":\"diag\",\"timestamp\":$(date +%s)000}"
    echo "   -> Published"
else
    echo "   -> MQTT credentials not found, skipping"
fi
echo ""

# Step 3: Wait and check if it was stored
sleep 2
echo "3. CHECKING IF REQUESTID WAS STORED"
NEW_ID=$(curl -s -H "Authorization: Bearer $HA_TOKEN" "http://$HA_HOST/api/states/input_text.claude_approval_request_id" | jq -r '.state')
echo "   input_text.claude_approval_request_id:"
echo "   -> $NEW_ID"

if [[ "$NEW_ID" == "$TEST_ID" ]]; then
    echo "   ✓ SUCCESS - requestId was stored!"
else
    echo "   ✗ FAILED - requestId NOT stored"
    echo "   Expected: $TEST_ID"
    echo "   Got: $NEW_ID"
fi
echo ""

# Step 4: Check automation last_triggered
echo "4. AUTOMATION TRIGGER STATUS"
LAST_TRIGGERED=$(curl -s -H "Authorization: Bearer $HA_TOKEN" "http://$HA_HOST/api/states/automation.claude_code_led_feedback_v2" | jq -r '.attributes.last_triggered')
echo "   last_triggered: $LAST_TRIGGERED"
echo ""

# Step 5: Check automation config - specifically the approval_request trigger
echo "5. CHECKING AUTOMATION CONFIG"
CONFIG=$(curl -s -H "Authorization: Bearer $HA_TOKEN" "http://$HA_HOST/api/config/automation/config/claude_code_led_feedback_v2")

if [[ -z "$CONFIG" || "$CONFIG" == "null" ]]; then
    echo "   ✗ Could not fetch automation config"
else
    # Check if approval_request trigger exists
    TRIGGERS=$(echo "$CONFIG" | jq -r '.triggers[]?.id // empty' 2>/dev/null)
    echo "   Available trigger IDs:"
    echo "$TRIGGERS" | sed 's/^/      /'

    if echo "$TRIGGERS" | grep -q "approval_request"; then
        echo "   ✓ approval_request trigger found"
        echo "$CONFIG" | jq '.trigger[] | select(.id == "approval_request")' 2>/dev/null
    else
        echo "   ✗ NO approval_request trigger!"
    fi
fi
echo ""

# Step 6: Dump raw config for manual inspection
echo "6. RAW AUTOMATION CONFIG (first 2000 chars)"
echo "$CONFIG" | head -c 2000
echo "..."

echo ""
echo "=== DIAGNOSIS COMPLETE ==="
