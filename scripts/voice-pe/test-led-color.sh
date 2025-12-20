#!/bin/bash
# Test LED segment with specific color
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../proxmox/homelab/.env"

[[ -f "$ENV_FILE" ]] && HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
[[ -z "$HA_TOKEN" ]] && { echo "ERROR: HA_TOKEN not found"; exit 1; }

HA_URL="${HA_URL:-http://192.168.1.122:8123}"
COLOR="${1:-red}"

case "$COLOR" in
    red)   R=255; G=0; B=0 ;;
    blue)  R=0; G=0; B=255 ;;
    green) R=0; G=255; B=0 ;;
    white) R=255; G=255; B=255 ;;
    off)   R=0; G=0; B=0 ;;
    *)     echo "Usage: $0 [red|blue|green|white|off]"; exit 1 ;;
esac

echo "=== Setting LEDs 0-11 to $COLOR ==="
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"start_led\": 0, \"end_led\": 11, \"red\": $R, \"green\": $G, \"blue\": $B}" \
  "$HA_URL/api/services/esphome/home_assistant_voice_09f5a3_set_led_segment"
echo ""
