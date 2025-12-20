#!/bin/bash
# Fix the payload_template quoting issue in dial CW/CCW automations
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

[[ -z "$HA_TOKEN" ]] && { echo "ERROR: HA_TOKEN not found"; exit 1; }

HA_URL="http://192.168.1.122:8123"

echo "=== Fixing Payload Templates ==="

# The issue: payload_template with nested quotes isn't being parsed
# Solution: Use Jinja template properly with single quotes for the inner string

echo "1. Updating Dial CW automation..."
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    "$HA_URL/api/config/automation/config/claude_approval_dial_cw" \
    -d '{
  "alias": "Claude Approval - Dial CW (Approve)",
  "trigger": [{"platform": "event", "event_type": "esphome.voice_pe_dial", "event_data": {"direction": "clockwise"}}],
  "condition": [{"condition": "state", "entity_id": "input_boolean.claude_awaiting_approval", "state": "on"}],
  "action": [
    {"service": "light.turn_on", "target": {"entity_id": "light.home_assistant_voice_09f5a3_led_ring"}, "data": {"rgb_color": [0, 255, 0], "brightness": 255}},
    {"service": "tts.speak", "target": {"entity_id": "tts.piper"}, "data": {"media_player_entity_id": "media_player.home_assistant_voice_09f5a3_media_player", "message": "Approved"}},
    {"service": "mqtt.publish", "data": {"topic": "claude/approval-response", "payload": "{{ {\"requestId\": states(\"input_text.claude_approval_request_id\"), \"approved\": true} | to_json }}"}},
    {"service": "input_boolean.turn_off", "target": {"entity_id": "input_boolean.claude_awaiting_approval"}},
    {"delay": {"seconds": 2}},
    {"service": "light.turn_off", "target": {"entity_id": "light.home_assistant_voice_09f5a3_led_ring"}}
  ]
}' && echo " ✓"

echo "2. Updating Dial CCW automation..."
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    "$HA_URL/api/config/automation/config/claude_approval_dial_ccw" \
    -d '{
  "alias": "Claude Approval - Dial CCW (Reject)",
  "trigger": [{"platform": "event", "event_type": "esphome.voice_pe_dial", "event_data": {"direction": "anticlockwise"}}],
  "condition": [{"condition": "state", "entity_id": "input_boolean.claude_awaiting_approval", "state": "on"}],
  "action": [
    {"service": "light.turn_on", "target": {"entity_id": "light.home_assistant_voice_09f5a3_led_ring"}, "data": {"rgb_color": [255, 0, 0], "brightness": 255}},
    {"service": "tts.speak", "target": {"entity_id": "tts.piper"}, "data": {"media_player_entity_id": "media_player.home_assistant_voice_09f5a3_media_player", "message": "Rejected"}},
    {"service": "mqtt.publish", "data": {"topic": "claude/approval-response", "payload": "{{ {\"requestId\": states(\"input_text.claude_approval_request_id\"), \"approved\": false} | to_json }}"}},
    {"service": "input_boolean.turn_off", "target": {"entity_id": "input_boolean.claude_awaiting_approval"}},
    {"delay": {"seconds": 2}},
    {"service": "light.turn_off", "target": {"entity_id": "light.home_assistant_voice_09f5a3_led_ring"}}
  ]
}' && echo " ✓"

echo "3. Updating Timeout automation..."
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    "$HA_URL/api/config/automation/config/claude_approval_timeout" \
    -d '{
  "alias": "Claude Approval - Timeout",
  "trigger": [{"platform": "event", "event_type": "timer.finished", "event_data": {"entity_id": "timer.claude_approval_timeout"}}],
  "condition": [{"condition": "state", "entity_id": "input_boolean.claude_awaiting_approval", "state": "on"}],
  "action": [
    {"service": "light.turn_on", "target": {"entity_id": "light.home_assistant_voice_09f5a3_led_ring"}, "data": {"rgb_color": [255, 0, 0], "brightness": 255}},
    {"service": "tts.speak", "target": {"entity_id": "tts.piper"}, "data": {"media_player_entity_id": "media_player.home_assistant_voice_09f5a3_media_player", "message": "Request timed out"}},
    {"service": "mqtt.publish", "data": {"topic": "claude/approval-response", "payload": "{{ {\"requestId\": states(\"input_text.claude_approval_request_id\"), \"approved\": false, \"reason\": \"timeout\"} | to_json }}"}},
    {"service": "input_boolean.turn_off", "target": {"entity_id": "input_boolean.claude_awaiting_approval"}},
    {"delay": {"seconds": 2}},
    {"service": "light.turn_off", "target": {"entity_id": "light.home_assistant_voice_09f5a3_led_ring"}}
  ]
}' && echo " ✓"

curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/services/automation/reload" >/dev/null && echo "✓ Reloaded"
