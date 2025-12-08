#!/bin/bash
# Create sentence trigger automation for natural voice commands

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../../proxmox/homelab/.env"
HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2)
HA_URL="http://192.168.4.240:8123"

echo "═══════════════════════════════════════════════════════"
echo "  Creating Sentence Trigger for Notifications"
echo "═══════════════════════════════════════════════════════"
echo ""

SENTENCE_AUTOMATION=$(cat <<'ENDJSON'
{
  "alias": "Voice - Check Notifications",
  "description": "Natural voice command to check notifications",
  "trigger": [
    {
      "platform": "conversation",
      "command": [
        "what's my notification",
        "whats my notification",
        "what is my notification",
        "any notifications",
        "do I have notifications",
        "do I have any notifications",
        "check notifications",
        "check my notifications",
        "read notifications",
        "read my notification"
      ]
    }
  ],
  "action": [
    {
      "service": "script.turn_on",
      "target": {
        "entity_id": "script.get_pending_notification"
      }
    }
  ],
  "mode": "single"
}
ENDJSON
)

echo "1️⃣  Creating sentence trigger automation..."
RESPONSE=$(curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d "$SENTENCE_AUTOMATION" \
    "$HA_URL/api/config/automation/config/voice_check_notifications" 2>&1)

if echo "$RESPONSE" | grep -q "error"; then
    echo "   Trying PUT instead..."
    curl -s -X PUT \
        -H "Authorization: Bearer $HA_TOKEN" \
        -H "Content-Type: application/json" \
        -d "$SENTENCE_AUTOMATION" \
        "$HA_URL/api/config/automation/config/voice_check_notifications" > /dev/null 2>&1
fi
echo "   ✅ Created"

echo ""
echo "2️⃣  Reloading automations..."
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/services/automation/reload" > /dev/null
echo "   ✅ Reloaded"

echo ""
echo "3️⃣  Resetting test state..."
curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"entity_id": "input_boolean.has_pending_notification"}' \
    "$HA_URL/api/services/input_boolean/turn_off" > /dev/null

curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"entity_id": "light.home_assistant_voice_09f5a3_led_ring"}' \
    "$HA_URL/api/services/light/turn_off" > /dev/null
echo "   ✅ Reset"

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  Done! Now you can say:"
echo ""
echo "  'Okay Nabu, what's my notification?'"
echo "  'Okay Nabu, any notifications?'"
echo "  'Okay Nabu, check notifications'"
echo "═══════════════════════════════════════════════════════"
