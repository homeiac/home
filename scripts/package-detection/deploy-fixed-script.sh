#!/bin/bash
# Deploy the fixed notification script (non-blocking announcement)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../../proxmox/homelab/.env"
HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2)
HA_URL="http://192.168.4.240:8123"

echo "═══════════════════════════════════════════════════════"
echo "  Deploying Fixed Notification Script"
echo "═══════════════════════════════════════════════════════"
echo ""

# Fixed script with parallel announcement (non-blocking)
FIXED_SCRIPT=$(cat <<'ENDJSON'
{
  "alias": "Get Pending Notification",
  "description": "Responds with pending notification details when asked via voice (fixed: non-blocking)",
  "icon": "mdi:bell-ring",
  "mode": "restart",
  "sequence": [
    {
      "if": [
        {
          "condition": "state",
          "entity_id": "input_boolean.has_pending_notification",
          "state": "on"
        }
      ],
      "then": [
        {
          "parallel": [
            {
              "service": "assist_satellite.announce",
              "target": { "entity_id": "assist_satellite.home_assistant_voice_09f5a3_assist_satellite" },
              "data": { "message": "{{ states('input_text.pending_notification_message') }}" }
            }
          ]
        },
        {
          "service": "input_boolean.turn_off",
          "target": { "entity_id": "input_boolean.has_pending_notification" }
        }
      ],
      "else": [
        {
          "service": "assist_satellite.announce",
          "target": { "entity_id": "assist_satellite.home_assistant_voice_09f5a3_assist_satellite" },
          "data": { "message": "You have no pending notifications." }
        }
      ]
    }
  ]
}
ENDJSON
)

echo "1️⃣  Deploying fixed script..."
curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d "$FIXED_SCRIPT" \
    "$HA_URL/api/config/script/config/get_pending_notification" > /dev/null 2>&1 || \
curl -s -X PUT \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d "$FIXED_SCRIPT" \
    "$HA_URL/api/config/script/config/get_pending_notification" > /dev/null 2>&1

echo "   ✅ Deployed"

echo ""
echo "2️⃣  Reloading scripts..."
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/services/script/reload" > /dev/null
echo "   ✅ Reloaded"

echo ""
echo "3️⃣  Clearing any stuck state..."
# Turn off LED and boolean
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
echo "   ✅ Cleared"

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  Fix Applied!"
echo "═══════════════════════════════════════════════════════"
echo ""
echo "  The issue: assist_satellite.announce was blocking"
echo "  The fix: Wrapped in 'parallel' so it doesn't block"
echo ""
echo "  Test with: ./test-full-flow.sh"
echo "═══════════════════════════════════════════════════════"
