#!/bin/bash
# Debug the speak automation
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

HA_HOST="${HA_HOST:-homeassistant.maas}"

echo "=== Debug Speak Automation ==="
echo ""

echo "1. Last triggered:"
curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "http://$HA_HOST:8123/api/states/automation.claude_speak_response" | jq '{state, last_triggered: .attributes.last_triggered}'

echo ""
echo "2. Testing with direct MQTT payload simulation..."
echo "   Publishing a fake result message..."

# Get MQTT creds
MQTT_USER=$(grep "^MQTT_USER=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
MQTT_PASS=$(grep "^MQTT_PASS=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')

# Send a test result message directly
mosquitto_pub -h "$HA_HOST" -p 1883 -u "$MQTT_USER" -P "$MQTT_PASS" \
    -t "claude/home/response" \
    -m '{"type":"chunk","content":{"type":"claude-response","data":{"type":"result","result":"This is a test response"}}}'

sleep 3

echo ""
echo "3. Check if automation triggered:"
curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "http://$HA_HOST:8123/api/states/automation.claude_speak_response" | jq '{state, last_triggered: .attributes.last_triggered}'

echo ""
echo "Did you hear 'This is a test response'?"
