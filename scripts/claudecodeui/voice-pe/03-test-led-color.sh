#!/bin/bash
# Test Voice PE LED ring color control
# Since effects aren't exposed, we use RGB colors to indicate state
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

# Load HA_TOKEN from .env
if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

if [[ -z "$HA_TOKEN" ]]; then
    echo "ERROR: HA_TOKEN not found"
    exit 1
fi

HA_HOST="${HA_HOST:-homeassistant.maas}"
LED_ENTITY="light.home_assistant_voice_09f5a3_led_ring"

COLOR_NAME="${1:-thinking}"

# Get RGB for color name (bash 3.x compatible)
get_rgb() {
    case "$1" in
        thinking) echo "24,187,242" ;;     # Cyan/blue - Voice PE default thinking color
        waiting)  echo "255,165,0" ;;      # Amber - waiting for approval
        approve)  echo "0,255,0" ;;        # Green - approved
        reject)   echo "255,0,0" ;;        # Red - rejected
        off)      echo "" ;;
        *)        echo "" ;;
    esac
}

echo "=== Voice PE LED Color Test ==="
echo "Entity: $LED_ENTITY"
echo "Color: $COLOR_NAME"
echo ""

if [[ "$COLOR_NAME" == "off" ]]; then
    echo "Turning LED off..."
    curl -s -X POST \
        -H "Authorization: Bearer $HA_TOKEN" \
        -H "Content-Type: application/json" \
        -d "{\"entity_id\": \"$LED_ENTITY\"}" \
        "http://$HA_HOST:8123/api/services/light/turn_off" | jq '.'
else
    RGB=$(get_rgb "$COLOR_NAME")
    if [[ -z "$RGB" ]]; then
        echo "Unknown color: $COLOR_NAME"
        echo "Available: thinking, waiting, approve, reject, off"
        exit 1
    fi

    echo "Setting LED to RGB: $RGB"
    curl -s -X POST \
        -H "Authorization: Bearer $HA_TOKEN" \
        -H "Content-Type: application/json" \
        -d "{
            \"entity_id\": \"$LED_ENTITY\",
            \"rgb_color\": [$RGB],
            \"brightness\": 170
        }" \
        "http://$HA_HOST:8123/api/services/light/turn_on" | jq '.'
fi

echo ""
echo "=== Done ==="
echo ""
echo "Usage:"
echo "  $0 thinking   # Cyan pulse (processing)"
echo "  $0 waiting    # Amber (awaiting approval)"
echo "  $0 approve    # Green (approved)"
echo "  $0 reject     # Red (rejected)"
echo "  $0 off        # Turn off"
