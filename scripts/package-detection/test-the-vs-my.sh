#!/bin/bash
# Test "the" vs "my" in notification queries

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
echo "  Testing 'the' vs 'my' in Notification Queries"
echo "========================================================"
echo ""

# Reset state
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    -d '{"entity_id": "input_text.pending_notification_message", "value": "TEST-MESSAGE-FOR-PATTERN"}' \
    "$HA_URL/api/services/input_text/set_value" > /dev/null
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    -d '{"entity_id": "input_boolean.has_pending_notification"}' \
    "$HA_URL/api/services/input_boolean/turn_on" > /dev/null

TESTS=(
    "what is the notification"
    "what is my notification"
    "what's the notification"
    "what's my notification"
    "whats the notification"
    "whats my notification"
    "tell me the notification"
    "tell me my notification"
    "read the notification"
    "read my notification"
    "get the notification"
    "get my notification"
    "notification please"
    "notifications"
)

for phrase in "${TESTS[@]}"; do
    # Reset boolean
    curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
        -d '{"entity_id": "input_boolean.has_pending_notification"}' \
        "$HA_URL/api/services/input_boolean/turn_on" > /dev/null

    BEFORE=$(curl -s -H "Authorization: Bearer $HA_TOKEN" \
        "$HA_URL/api/states/script.get_pending_notification" | jq -r '.attributes.last_triggered')

    RESPONSE=$(curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
        -d "{\"text\": \"$phrase\", \"language\": \"en\"}" \
        "$HA_URL/api/conversation/process")

    SPEECH=$(echo "$RESPONSE" | jq -r '.response.speech.plain.speech // "N/A"')
    RESP_TYPE=$(echo "$RESPONSE" | jq -r '.response.response_type // "N/A"')

    AFTER=$(curl -s -H "Authorization: Bearer $HA_TOKEN" \
        "$HA_URL/api/states/script.get_pending_notification" | jq -r '.attributes.last_triggered')

    TRIGGERED=""
    if [[ "$BEFORE" != "$AFTER" ]]; then
        TRIGGERED="✓"
    else
        TRIGGERED="✗"
    fi

    printf "%-35s | %-12s | %s | %s\n" "$phrase" "$RESP_TYPE" "$TRIGGERED" "$SPEECH"
    sleep 0.5
done

echo ""
echo "========================================================"
echo "Legend: ✓ = script triggered, ✗ = script NOT triggered"
echo "========================================================"
