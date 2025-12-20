#!/bin/bash
# Deploy Claude approval automation to Home Assistant
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

[[ -z "$HA_TOKEN" ]] && { echo "ERROR: HA_TOKEN not found"; exit 1; }

HA_URL="http://192.168.1.122:8123"

echo "=== Deploying Claude Approval Automation ==="
echo ""

# Step 1: Create input_boolean helper
echo "1. Creating input_boolean.claude_awaiting_approval..."
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    "$HA_URL/api/services/input_boolean/create" \
    -d '{"name": "Claude Awaiting Approval", "icon": "mdi:robot"}' 2>/dev/null || true

# Check if it exists by trying to get its state
if curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/states/input_boolean.claude_awaiting_approval" | grep -q "entity_id"; then
    echo "   ✓ input_boolean.claude_awaiting_approval exists"
else
    echo "   ⚠ Need to create manually in HA Settings → Devices & Services → Helpers"
    echo "   Create Toggle: Name='Claude Awaiting Approval', Icon='mdi:robot'"
fi

# Step 2: Create timer helper
echo ""
echo "2. Creating timer.claude_approval_timeout..."
if curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/states/timer.claude_approval_timeout" | grep -q "entity_id"; then
    echo "   ✓ timer.claude_approval_timeout exists"
else
    echo "   ⚠ Need to create manually in HA Settings → Devices & Services → Helpers"
    echo "   Create Timer: Name='Claude Approval Timeout', Duration='00:00:30'"
fi

echo ""
echo "3. Automation YAML to add to HA:"
echo ""
cat << 'YAML'
# Add to configuration.yaml or automations.yaml

automation:
  - alias: "Claude Approval - Dial CW (Approve)"
    id: claude_approval_dial_cw
    trigger:
      - platform: event
        event_type: esphome.voice_pe_dial
        event_data:
          direction: clockwise
    condition:
      - condition: state
        entity_id: input_boolean.claude_awaiting_approval
        state: "on"
    action:
      - service: light.turn_on
        target:
          entity_id: light.home_assistant_voice_09f5a3_led_ring
        data:
          rgb_color: [0, 255, 0]
          brightness: 255
      - service: tts.speak
        target:
          entity_id: tts.piper
        data:
          media_player_entity_id: media_player.home_assistant_voice_09f5a3_media_player
          message: "Approved"
      - service: mqtt.publish
        data:
          topic: claude/approval-response
          payload: '{"approved": true}'
      - service: input_boolean.turn_off
        target:
          entity_id: input_boolean.claude_awaiting_approval
      - delay: 2
      - service: light.turn_off
        target:
          entity_id: light.home_assistant_voice_09f5a3_led_ring

  - alias: "Claude Approval - Dial CCW (Reject)"
    id: claude_approval_dial_ccw
    trigger:
      - platform: event
        event_type: esphome.voice_pe_dial
        event_data:
          direction: anticlockwise
    condition:
      - condition: state
        entity_id: input_boolean.claude_awaiting_approval
        state: "on"
    action:
      - service: light.turn_on
        target:
          entity_id: light.home_assistant_voice_09f5a3_led_ring
        data:
          rgb_color: [255, 0, 0]
          brightness: 255
      - service: tts.speak
        target:
          entity_id: tts.piper
        data:
          media_player_entity_id: media_player.home_assistant_voice_09f5a3_media_player
          message: "Rejected"
      - service: mqtt.publish
        data:
          topic: claude/approval-response
          payload: '{"approved": false}'
      - service: input_boolean.turn_off
        target:
          entity_id: input_boolean.claude_awaiting_approval
      - delay: 2
      - service: light.turn_off
        target:
          entity_id: light.home_assistant_voice_09f5a3_led_ring

  - alias: "Claude Approval - Start Timer"
    id: claude_approval_start_timer
    trigger:
      - platform: state
        entity_id: input_boolean.claude_awaiting_approval
        to: "on"
    action:
      - service: light.turn_on
        target:
          entity_id: light.home_assistant_voice_09f5a3_led_ring
        data:
          rgb_color: [255, 165, 0]
          brightness: 200
      - service: tts.speak
        target:
          entity_id: tts.piper
        data:
          media_player_entity_id: media_player.home_assistant_voice_09f5a3_media_player
          message: "Approve or reject within 30 seconds"
      - service: timer.start
        target:
          entity_id: timer.claude_approval_timeout

  - alias: "Claude Approval - Timeout"
    id: claude_approval_timeout
    trigger:
      - platform: event
        event_type: timer.finished
        event_data:
          entity_id: timer.claude_approval_timeout
    condition:
      - condition: state
        entity_id: input_boolean.claude_awaiting_approval
        state: "on"
    action:
      - service: light.turn_on
        target:
          entity_id: light.home_assistant_voice_09f5a3_led_ring
        data:
          rgb_color: [255, 0, 0]
          brightness: 255
      - service: tts.speak
        target:
          entity_id: tts.piper
        data:
          media_player_entity_id: media_player.home_assistant_voice_09f5a3_media_player
          message: "Request timed out"
      - service: mqtt.publish
        data:
          topic: claude/approval-response
          payload: '{"approved": false, "reason": "timeout"}'
      - service: input_boolean.turn_off
        target:
          entity_id: input_boolean.claude_awaiting_approval
      - delay: 2
      - service: light.turn_off
        target:
          entity_id: light.home_assistant_voice_09f5a3_led_ring

  - alias: "Claude Approval - Cancel Timer"
    id: claude_approval_cancel_timer
    trigger:
      - platform: state
        entity_id: input_boolean.claude_awaiting_approval
        to: "off"
    action:
      - service: timer.cancel
        target:
          entity_id: timer.claude_approval_timeout
YAML

echo ""
echo "=== Next Steps ==="
echo "1. Create helpers in HA UI (if not exists)"
echo "2. Add automations via HA UI or YAML"
echo "3. Test: Turn on input_boolean.claude_awaiting_approval and rotate dial"
