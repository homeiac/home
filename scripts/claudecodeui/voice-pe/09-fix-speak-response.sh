#!/bin/bash
# Use new simplified 'answer' message type
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

[[ -z "$HA_TOKEN" ]] && { echo "ERROR: HA_TOKEN not found"; exit 1; }

HA_URL="http://192.168.1.122:8123"

echo "=== Update Speak Response for 'answer' type ==="

curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    "$HA_URL/api/config/automation/config/claude_speak_response" \
    -d '{
  "alias": "Claude Speak Response",
  "mode": "single",
  "trigger": [{"platform": "mqtt", "topic": "claude/home/response"}],
  "condition": [
    {
      "condition": "template",
      "value_template": "{{ trigger.payload_json.type == \"answer\" and trigger.payload_json.text is defined }}"
    }
  ],
  "action": [
    {
      "service": "tts.speak",
      "target": {"entity_id": "tts.piper"},
      "data": {
        "media_player_entity_id": "media_player.home_assistant_voice_09f5a3_media_player",
        "message": "{{ trigger.payload_json.text | truncate(250) }}"
      }
    }
  ]
}' && echo "✓ Automation updated"

# Remove debug automation
curl -s -X DELETE -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/config/automation/config/claude_debug_payload" 2>/dev/null && echo "✓ Debug automation removed" || true

curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/services/automation/reload" >/dev/null && echo "✓ Reloaded"

echo ""
echo "Now redeploy ClaudeCodeUI to pick up the code change"
