#!/bin/bash
# Subscribe to Claude response topic to see what's being published
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

echo "=== Subscribing to Claude MQTT topics ==="
echo "Press Ctrl+C to stop"
echo ""
echo "Listening for responses on:"
echo "  - claude/home/response"
echo "  - claude/home/status"
echo "  - claude/#"
echo ""

# Subscribe to all claude topics
mosquitto_sub -h "$MQTT_HOST" -p 1883 $MQTT_AUTH -t "claude/#" -v
