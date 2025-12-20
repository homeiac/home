#!/bin/bash
# Create Claude approval automations via HA API
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

[[ -z "$HA_TOKEN" ]] && { echo "ERROR: HA_TOKEN not found"; exit 1; }

HA_URL="http://192.168.1.122:8123"

echo "=== Creating Claude Approval Automations ==="

# Automation 1: Dial CW (Approve)
echo "1. Creating 'Dial CW - Approve' automation..."
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    "$HA_URL/api/config/automation/config/claude_approval_dial_cw" \
    -d '{
  "alias": "Claude Approval - Dial CW (Approve)",
  "trigger": [{"platform": "event", "event_type": "esphome.voice_pe_dial", "event_data": {"direction": "clockwise"}}],
  "condition": [{"condition": "state", "entity_id": "input_boolean.claude_awaiting_approval", "state": "on"}],
  "action": [
    {"service": "light.turn_on", "target": {"entity_id": "light.home_assistant_voice_09f5a3_led_ring"}, "data": {"rgb_color": [0, 255, 0], "brightness": 255}},
    {"service": "tts.speak", "target": {"entity_id": "tts.piper"}, "data": {"media_player_entity_id": "media_player.home_assistant_voice_09f5a3_media_player", "message": "Approved"}},
    {"service": "mqtt.publish", "data": {"topic": "claude/approval-response", "payload": "{\"approved\": true}"}},
    {"service": "input_boolean.turn_off", "target": {"entity_id": "input_boolean.claude_awaiting_approval"}},
    {"delay": {"seconds": 2}},
    {"service": "light.turn_off", "target": {"entity_id": "light.home_assistant_voice_09f5a3_led_ring"}}
  ]
}' && echo " ✓"

# Automation 2: Dial CCW (Reject)
echo "2. Creating 'Dial CCW - Reject' automation..."
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    "$HA_URL/api/config/automation/config/claude_approval_dial_ccw" \
    -d '{
  "alias": "Claude Approval - Dial CCW (Reject)",
  "trigger": [{"platform": "event", "event_type": "esphome.voice_pe_dial", "event_data": {"direction": "anticlockwise"}}],
  "condition": [{"condition": "state", "entity_id": "input_boolean.claude_awaiting_approval", "state": "on"}],
  "action": [
    {"service": "light.turn_on", "target": {"entity_id": "light.home_assistant_voice_09f5a3_led_ring"}, "data": {"rgb_color": [255, 0, 0], "brightness": 255}},
    {"service": "tts.speak", "target": {"entity_id": "tts.piper"}, "data": {"media_player_entity_id": "media_player.home_assistant_voice_09f5a3_media_player", "message": "Rejected"}},
    {"service": "mqtt.publish", "data": {"topic": "claude/approval-response", "payload": "{\"approved\": false}"}},
    {"service": "input_boolean.turn_off", "target": {"entity_id": "input_boolean.claude_awaiting_approval"}},
    {"delay": {"seconds": 2}},
    {"service": "light.turn_off", "target": {"entity_id": "light.home_assistant_voice_09f5a3_led_ring"}}
  ]
}' && echo " ✓"

# Automation 3: Start Timer
echo "3. Creating 'Start Timer' automation..."
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    "$HA_URL/api/config/automation/config/claude_approval_start_timer" \
    -d '{
  "alias": "Claude Approval - Start Timer",
  "trigger": [{"platform": "state", "entity_id": "input_boolean.claude_awaiting_approval", "to": "on"}],
  "action": [
    {"service": "light.turn_on", "target": {"entity_id": "light.home_assistant_voice_09f5a3_led_ring"}, "data": {"rgb_color": [255, 165, 0], "brightness": 200}},
    {"service": "tts.speak", "target": {"entity_id": "tts.piper"}, "data": {"media_player_entity_id": "media_player.home_assistant_voice_09f5a3_media_player", "message": "Approve or reject within 30 seconds"}},
    {"service": "timer.start", "target": {"entity_id": "timer.claude_approval_timeout"}}
  ]
}' && echo " ✓"

# Automation 4: Timeout
echo "4. Creating 'Timeout' automation..."
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    "$HA_URL/api/config/automation/config/claude_approval_timeout" \
    -d '{
  "alias": "Claude Approval - Timeout",
  "trigger": [{"platform": "event", "event_type": "timer.finished", "event_data": {"entity_id": "timer.claude_approval_timeout"}}],
  "condition": [{"condition": "state", "entity_id": "input_boolean.claude_awaiting_approval", "state": "on"}],
  "action": [
    {"service": "light.turn_on", "target": {"entity_id": "light.home_assistant_voice_09f5a3_led_ring"}, "data": {"rgb_color": [255, 0, 0], "brightness": 255}},
    {"service": "tts.speak", "target": {"entity_id": "tts.piper"}, "data": {"media_player_entity_id": "media_player.home_assistant_voice_09f5a3_media_player", "message": "Request timed out"}},
    {"service": "mqtt.publish", "data": {"topic": "claude/approval-response", "payload": "{\"approved\": false, \"reason\": \"timeout\"}"}},
    {"service": "input_boolean.turn_off", "target": {"entity_id": "input_boolean.claude_awaiting_approval"}},
    {"delay": {"seconds": 2}},
    {"service": "light.turn_off", "target": {"entity_id": "light.home_assistant_voice_09f5a3_led_ring"}}
  ]
}' && echo " ✓"

# Automation 5: Cancel Timer
echo "5. Creating 'Cancel Timer' automation..."
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    "$HA_URL/api/config/automation/config/claude_approval_cancel_timer" \
    -d '{
  "alias": "Claude Approval - Cancel Timer",
  "trigger": [{"platform": "state", "entity_id": "input_boolean.claude_awaiting_approval", "to": "off"}],
  "action": [
    {"service": "timer.cancel", "target": {"entity_id": "timer.claude_approval_timeout"}}
  ]
}' && echo " ✓"

echo ""
echo "=== Reloading automations ==="
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/services/automation/reload" && echo "✓ Automations reloaded"

echo ""
echo "=== Done! Test with: ==="
echo "curl -X POST -H 'Authorization: Bearer \$HA_TOKEN' '$HA_URL/api/services/input_boolean/turn_on' -d '{\"entity_id\": \"input_boolean.claude_awaiting_approval\"}'"
