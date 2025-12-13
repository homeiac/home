#!/bin/bash
# Test different phrasings with Ollama conversation

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
echo "  Testing Different Phrasings with Ollama"
echo "========================================================"
echo ""

# First set a known state
TEST_MSG="TEST-$(date +%s)-UNIQUE-PACKAGE"
echo "Setting test notification: $TEST_MSG"
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    -d "{\"entity_id\": \"input_text.pending_notification_message\", \"value\": \"$TEST_MSG\"}" \
    "$HA_URL/api/services/input_text/set_value" > /dev/null

curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    -d '{"entity_id": "input_boolean.has_pending_notification"}' \
    "$HA_URL/api/services/input_boolean/turn_on" > /dev/null

# Verify state
ACTUAL=$(curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/states/input_text.pending_notification_message" | jq -r '.state')
echo "Verified state: $ACTUAL"
echo ""

# Test different phrasings
PHRASINGS=(
    "what is the notification"
    "check my notifications"
    "do I have any notifications"
    "what is the state of has_pending_notification"
    "what is input_text.pending_notification_message"
    "read input_text.pending_notification_message"
    "run script.get_pending_notification"
    "execute get pending notification"
    "call script get pending notification"
    "turn off has_pending_notification"
)

for phrase in "${PHRASINGS[@]}"; do
    echo "========================================================"
    echo "Testing: '$phrase'"
    echo "========================================================"

    RESPONSE=$(curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
        -d "{\"text\": \"$phrase\", \"language\": \"en\"}" \
        "$HA_URL/api/conversation/process")

    SPEECH=$(echo "$RESPONSE" | jq -r '.response.speech.plain.speech // "N/A"')
    RESP_TYPE=$(echo "$RESPONSE" | jq -r '.response.response_type // "N/A"')

    echo "Response Type: $RESP_TYPE"
    echo "Speech: $SPEECH"

    # Check if contains test value
    if echo "$SPEECH" | grep -q "$TEST_MSG"; then
        echo "✓ CONTAINS TEST VALUE!"
    fi

    echo ""
    sleep 1
done

# Check if script was triggered
AFTER_TRIGGERED=$(curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/states/script.get_pending_notification" | jq -r '.attributes.last_triggered // "never"')
echo "========================================================"
echo "Script last_triggered: $AFTER_TRIGGERED"
echo "========================================================"
