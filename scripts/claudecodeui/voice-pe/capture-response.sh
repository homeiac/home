#!/bin/bash
# Capture actual Claude MQTT response to see the format
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    MQTT_USER=$(grep "^MQTT_USER=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
    MQTT_PASS=$(grep "^MQTT_PASS=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

MQTT_HOST="${MQTT_HOST:-homeassistant.maas}"

echo "=== Capturing Claude Response ==="
echo "Subscribing for 20 seconds..."
echo "Will send a test command in 3 seconds..."
echo ""

# Start subscriber in background, save to file
timeout 20 mosquitto_sub -h "$MQTT_HOST" -p 1883 -u "$MQTT_USER" -P "$MQTT_PASS" \
    -t "claude/home/response" -v > /tmp/mqtt_capture.txt 2>&1 &
SUB_PID=$!

sleep 3

echo "Sending test command..."
mosquitto_pub -h "$MQTT_HOST" -p 1883 -u "$MQTT_USER" -P "$MQTT_PASS" \
    -t "claude/command" \
    -m '{"source":"capture-test","server":"home","type":"chat","message":"Say just the word hello"}'

echo "Waiting for response..."
wait $SUB_PID 2>/dev/null || true

echo ""
echo "=== Captured responses (showing result message only) ==="
grep -i "result" /tmp/mqtt_capture.txt | head -3 || echo "No result found"

echo ""
echo "=== Full capture ==="
cat /tmp/mqtt_capture.txt | head -20
