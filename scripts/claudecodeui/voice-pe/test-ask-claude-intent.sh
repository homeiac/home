#!/bin/bash
# Test "Ask Claude" voice intent via conversation API
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
    MQTT_USER=$(grep "^MQTT_USER=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
    MQTT_PASS=$(grep "^MQTT_PASS=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

HA_HOST="${HA_HOST:-homeassistant.maas}"
MQTT_HOST="${MQTT_HOST:-homeassistant.maas}"
QUERY="${1:-what time is it}"

echo "=== Test Ask Claude Intent ==="
echo "Query: $QUERY"
echo ""

# Start MQTT subscriber in background
echo "1. Starting MQTT subscriber on claude/command..."
timeout 10 mosquitto_sub -h "$MQTT_HOST" -p 1883 -u "$MQTT_USER" -P "$MQTT_PASS" \
    -t "claude/command" -v > /tmp/mqtt_intent_test.txt 2>&1 &
SUB_PID=$!

sleep 1

# Send conversation request
echo "2. Sending conversation: 'ask claude $QUERY'"
RESPONSE=$(curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"text\": \"ask claude $QUERY\", \"language\": \"en\"}" \
    "http://$HA_HOST:8123/api/conversation/process")

echo "3. Conversation response:"
echo "$RESPONSE" | jq '{response: .response.speech.plain.speech, intent: .response.data.code}'
echo ""

# Wait for MQTT message
sleep 2
kill $SUB_PID 2>/dev/null || true

echo "4. MQTT message received:"
cat /tmp/mqtt_intent_test.txt || echo "   (no message)"
