#!/bin/bash
# Test the full package notification flow

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../../proxmox/homelab/.env"
HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2)
HA_URL="http://192.168.4.240:8123"

echo "═══════════════════════════════════════════════════════"
echo "  Testing Package Notification Flow"
echo "═══════════════════════════════════════════════════════"
echo ""

TIMESTAMP=$(date +"%I:%M %p")

echo "1️⃣  Setting notification message..."
curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"entity_id\": \"input_text.pending_notification_message\", \"value\": \"Package delivered at $TIMESTAMP by Amazon driver in blue vest\"}" \
    "$HA_URL/api/services/input_text/set_value" > /dev/null
echo "   ✅ Message: Package delivered at $TIMESTAMP by Amazon driver in blue vest"

echo ""
echo "2️⃣  Setting notification type..."
curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"entity_id": "input_text.pending_notification_type", "value": "package"}' \
    "$HA_URL/api/services/input_text/set_value" > /dev/null
echo "   ✅ Type: package"

echo ""
echo "3️⃣  Turning on notification flag..."
curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"entity_id": "input_boolean.has_pending_notification"}' \
    "$HA_URL/api/services/input_boolean/turn_on" > /dev/null
echo "   ✅ Flag: on"

echo ""
echo "4️⃣  Turning on LED (blue pulse)..."
curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"entity_id": "light.home_assistant_voice_09f5a3_led_ring", "rgb_color": [0, 100, 255], "brightness": 200}' \
    "$HA_URL/api/services/light/turn_on" > /dev/null
echo "   ✅ LED: blue"

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  TEST ACTIVE!"
echo "═══════════════════════════════════════════════════════"
echo ""
echo "  🔵 LED should be pulsing blue now"
echo ""
echo "  Say: 'Okay Nabu, what's my notification?'"
echo ""
echo "  Expected response:"
echo "  'Package delivered at $TIMESTAMP by Amazon driver in blue vest'"
echo ""
echo "  LED should turn off after response."
echo "═══════════════════════════════════════════════════════"
