#!/bin/bash
# Test Voice PE LED ring control
# Usage: ./test-voice-pe-led.sh [color] [seconds]
# Colors: blue, green, red, white, off
# Default: blue pulse for 5 seconds

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../../proxmox/homelab/.env"

HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2)
HA_URL="http://192.168.4.240:8123"

LED_ENTITY="light.home_assistant_voice_09f5a3_led_ring"
COLOR="${1:-blue}"
DURATION="${2:-5}"

# Color mapping
case "$COLOR" in
    blue)   RGB="[0, 100, 255]" ;;
    green)  RGB="[0, 255, 0]" ;;
    red)    RGB="[255, 0, 0]" ;;
    white)  RGB="[255, 255, 255]" ;;
    yellow) RGB="[255, 200, 0]" ;;
    purple) RGB="[150, 0, 255]" ;;
    off)    RGB="" ;;
    *)      RGB="[0, 100, 255]" ;;
esac

echo "=== Testing Voice PE LED Ring ==="
echo "Entity: $LED_ENTITY"
echo "Color: $COLOR"
echo "Duration: ${DURATION}s"
echo ""

if [[ "$COLOR" == "off" ]]; then
    echo "Turning LED off..."
    curl -s -X POST \
        -H "Authorization: Bearer $HA_TOKEN" \
        -H "Content-Type: application/json" \
        -d "{\"entity_id\": \"$LED_ENTITY\"}" \
        "$HA_URL/api/services/light/turn_off" > /dev/null

    echo "✅ LED turned off"
else
    echo "Turning LED on with $COLOR pulse..."
    curl -s -X POST \
        -H "Authorization: Bearer $HA_TOKEN" \
        -H "Content-Type: application/json" \
        -d "{
            \"entity_id\": \"$LED_ENTITY\",
            \"rgb_color\": $RGB,
            \"brightness\": 200
        }" \
        "$HA_URL/api/services/light/turn_on" > /dev/null

    echo "✅ LED on - waiting ${DURATION}s..."
    sleep "$DURATION"

    echo "Turning LED off..."
    curl -s -X POST \
        -H "Authorization: Bearer $HA_TOKEN" \
        -H "Content-Type: application/json" \
        -d "{\"entity_id\": \"$LED_ENTITY\"}" \
        "$HA_URL/api/services/light/turn_off" > /dev/null

    echo "✅ LED test complete"
fi
