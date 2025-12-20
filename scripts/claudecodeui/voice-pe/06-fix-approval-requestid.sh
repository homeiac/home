#!/bin/bash
# Fix approval flow to include requestId from ClaudeCodeUI
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

[[ -z "$HA_TOKEN" ]] && { echo "ERROR: HA_TOKEN not found"; exit 1; }

HA_URL="http://192.168.1.122:8123"

echo "=== Fixing Approval Flow with requestId ==="

# Check if input_text exists
echo "1. Checking for input_text.claude_approval_request_id..."
if curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/states/input_text.claude_approval_request_id" | grep -q "entity_id"; then
    echo "   ✓ Already exists"
else
    echo "   ⚠ Need to create: Settings → Helpers → Text"
    echo "   Name: 'Claude Approval Request ID'"
    echo "   Max length: 100"
fi

# Update Dial CW automation to include requestId
echo ""
echo "2. Updating 'Dial CW - Approve' with requestId..."
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    "$HA_URL/api/config/automation/config/claude_approval_dial_cw" \
    -d '{
  "alias": "Claude Approval - Dial CW (Approve)",
  "trigger": [{"platform": "event", "event_type": "esphome.voice_pe_dial", "event_data": {"direction": "clockwise"}}],
  "condition": [{"condition": "state", "entity_id": "input_boolean.claude_awaiting_approval", "state": "on"}],
  "action": [
    {"service": "light.turn_on", "target": {"entity_id": "light.home_assistant_voice_09f5a3_led_ring"}, "data": {"rgb_color": [0, 255, 0], "brightness": 255}},
    {"service": "tts.speak", "target": {"entity_id": "tts.piper"}, "data": {"media_player_entity_id": "media_player.home_assistant_voice_09f5a3_media_player", "message": "Approved"}},
    {"service": "mqtt.publish", "data": {"topic": "claude/approval-response", "payload_template": "{\"requestId\": \"{{ states(\"input_text.claude_approval_request_id\") }}\", \"approved\": true}"}},
    {"service": "input_boolean.turn_off", "target": {"entity_id": "input_boolean.claude_awaiting_approval"}},
    {"delay": {"seconds": 2}},
    {"service": "light.turn_off", "target": {"entity_id": "light.home_assistant_voice_09f5a3_led_ring"}}
  ]
}' && echo " ✓"

# Update Dial CCW automation to include requestId
echo "3. Updating 'Dial CCW - Reject' with requestId..."
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    "$HA_URL/api/config/automation/config/claude_approval_dial_ccw" \
    -d '{
  "alias": "Claude Approval - Dial CCW (Reject)",
  "trigger": [{"platform": "event", "event_type": "esphome.voice_pe_dial", "event_data": {"direction": "anticlockwise"}}],
  "condition": [{"condition": "state", "entity_id": "input_boolean.claude_awaiting_approval", "state": "on"}],
  "action": [
    {"service": "light.turn_on", "target": {"entity_id": "light.home_assistant_voice_09f5a3_led_ring"}, "data": {"rgb_color": [255, 0, 0], "brightness": 255}},
    {"service": "tts.speak", "target": {"entity_id": "tts.piper"}, "data": {"media_player_entity_id": "media_player.home_assistant_voice_09f5a3_media_player", "message": "Rejected"}},
    {"service": "mqtt.publish", "data": {"topic": "claude/approval-response", "payload_template": "{\"requestId\": \"{{ states(\"input_text.claude_approval_request_id\") }}\", \"approved\": false}"}},
    {"service": "input_boolean.turn_off", "target": {"entity_id": "input_boolean.claude_awaiting_approval"}},
    {"delay": {"seconds": 2}},
    {"service": "light.turn_off", "target": {"entity_id": "light.home_assistant_voice_09f5a3_led_ring"}}
  ]
}' && echo " ✓"

# Update Timeout automation to include requestId
echo "4. Updating 'Timeout' with requestId..."
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    "$HA_URL/api/config/automation/config/claude_approval_timeout" \
    -d '{
  "alias": "Claude Approval - Timeout",
  "trigger": [{"platform": "event", "event_type": "timer.finished", "event_data": {"entity_id": "timer.claude_approval_timeout"}}],
  "condition": [{"condition": "state", "entity_id": "input_boolean.claude_awaiting_approval", "state": "on"}],
  "action": [
    {"service": "light.turn_on", "target": {"entity_id": "light.home_assistant_voice_09f5a3_led_ring"}, "data": {"rgb_color": [255, 0, 0], "brightness": 255}},
    {"service": "tts.speak", "target": {"entity_id": "tts.piper"}, "data": {"media_player_entity_id": "media_player.home_assistant_voice_09f5a3_media_player", "message": "Request timed out"}},
    {"service": "mqtt.publish", "data": {"topic": "claude/approval-response", "payload_template": "{\"requestId\": \"{{ states(\"input_text.claude_approval_request_id\") }}\", \"approved\": false, \"reason\": \"timeout\"}"}},
    {"service": "input_boolean.turn_off", "target": {"entity_id": "input_boolean.claude_awaiting_approval"}},
    {"delay": {"seconds": 2}},
    {"service": "light.turn_off", "target": {"entity_id": "light.home_assistant_voice_09f5a3_led_ring"}}
  ]
}' && echo " ✓"

# Create automation to capture incoming approval requests
echo "5. Creating 'Capture Approval Request' automation..."
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    "$HA_URL/api/config/automation/config/claude_approval_capture_request" \
    -d '{
  "alias": "Claude Approval - Capture Request",
  "trigger": [{"platform": "mqtt", "topic": "claude/approval-request"}],
  "action": [
    {"service": "input_text.set_value", "target": {"entity_id": "input_text.claude_approval_request_id"}, "data": {"value": "{{ trigger.payload_json.requestId }}"}},
    {"service": "input_boolean.turn_on", "target": {"entity_id": "input_boolean.claude_awaiting_approval"}}
  ]
}' && echo " ✓"

echo ""
echo "=== Reloading automations ==="
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/services/automation/reload" && echo "✓ Automations reloaded"

echo ""
echo "=== Summary ==="
echo "1. Create input_text.claude_approval_request_id helper (if not exists)"
echo "2. Automations updated to include requestId in MQTT response"
echo "3. New automation captures requestId from incoming requests"
