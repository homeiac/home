#!/bin/bash
# Test the Claude Speak Response automation
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../proxmox/homelab/.env"

[[ -f "$ENV_FILE" ]] && {
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
    MQTT_USER=$(grep "^MQTT_USER=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
    MQTT_PASS=$(grep "^MQTT_PASS=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
}
[[ -z "$HA_TOKEN" ]] && { echo "ERROR: HA_TOKEN not found"; exit 1; }

HA_HOST="${HA_HOST:-homeassistant.maas}"
MESSAGE="${1:-This is a test message from Claude.}"

echo "=== Testing Claude Speak Response ==="
echo "Message: $MESSAGE"
echo ""

MQTT_AUTH=""
[[ -n "$MQTT_USER" && -n "$MQTT_PASS" ]] && MQTT_AUTH="-u $MQTT_USER -P $MQTT_PASS"

# Send response that triggers the speak automation
PAYLOAD="{\"type\":\"answer\",\"text\":\"$MESSAGE\"}"
echo "Publishing to claude/home/response..."
mosquitto_pub -h "$HA_HOST" -p 1883 $MQTT_AUTH -t "claude/home/response" -m "$PAYLOAD"

echo "Done. Voice PE should speak the message."
