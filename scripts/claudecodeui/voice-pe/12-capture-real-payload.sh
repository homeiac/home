#!/bin/bash
# Capture chunk messages specifically
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

HA_URL="http://192.168.1.122:8123"

echo "=== Debug: Capture ALL messages ==="

# Capture ALL mqtt messages (not filtered)
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    "$HA_URL/api/config/automation/config/claude_debug_payload" \
    -d '{
  "alias": "Claude Debug Payload",
  "mode": "queued",
  "max": 50,
  "trigger": [{"platform": "mqtt", "topic": "claude/home/response"}],
  "action": [
    {
      "service": "persistent_notification.create",
      "data": {
        "title": "Type: {{ trigger.payload_json.type }}",
        "message": "{{ trigger.payload[:800] }}"
      }
    }
  ]
}' && echo "✓ Updated"

curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/services/automation/reload" >/dev/null

echo ""
echo "Say 'ask claude what is two plus two' and check ALL notifications"
