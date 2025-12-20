#!/bin/bash
# Test if claudecodeui publishes responses to MQTT
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    MQTT_USER=$(grep "^MQTT_USER=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
    MQTT_PASS=$(grep "^MQTT_PASS=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

MQTT_HOST="${MQTT_HOST:-homeassistant.maas}"
MQTT_AUTH=""
[[ -n "$MQTT_USER" && -n "$MQTT_PASS" ]] && MQTT_AUTH="-u $MQTT_USER -P $MQTT_PASS"

echo "=== Testing MQTT Response Flow ==="
echo ""
echo "Step 1: Starting MQTT subscriber (10 second timeout)..."
timeout 15 mosquitto_sub -h "$MQTT_HOST" -p 1883 $MQTT_AUTH -t "claude/#" -v &
SUB_PID=$!

sleep 2

echo ""
echo "Step 2: Sending test command..."
mosquitto_pub -h "$MQTT_HOST" -p 1883 $MQTT_AUTH -t "claude/command" -m '{
  "source": "mqtt-test",
  "server": "home",
  "type": "chat",
  "message": "Say hello"
}'

echo "Command sent. Waiting for response..."
echo "(If no response appears, claudecodeui may not be publishing to MQTT)"
echo ""

wait $SUB_PID 2>/dev/null || true

echo ""
echo "=== Test Complete ==="
