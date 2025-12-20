#!/bin/bash
# Simulate a voice command to claudecodeui
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

MESSAGE="${1:-What is 2 plus 2}"

echo "=== Sending Voice Command to Claude ==="
echo "Message: $MESSAGE"
echo ""

# Proper command format for claudecodeui
PAYLOAD=$(cat <<EOF
{
  "source": "voice_pe",
  "server": "home",
  "type": "chat",
  "message": "$MESSAGE"
}
EOF
)

echo "Publishing to claude/command..."
mosquitto_pub -h "$MQTT_HOST" -p 1883 $MQTT_AUTH -t "claude/command" -m "$PAYLOAD"

echo "Command sent! Watch:"
echo "  - Voice PE LED should turn CYAN (thinking)"
echo "  - claudecodeui logs for response"
echo ""
echo "Check logs: KUBECONFIG=~/kubeconfig kubectl logs -n claudecodeui deployment/claudecodeui-blue -f"
