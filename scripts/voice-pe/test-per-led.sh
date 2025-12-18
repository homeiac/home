#!/bin/bash
# Test LED effects on Voice PE
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../proxmox/homelab/.env"
HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
HA_URL="http://192.168.1.122:8123"
ENTITY="light.home_assistant_voice_09f5a3_led_ring"

effect="${1:-Progress 3}"

echo "=== Testing effect: $effect ==="
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"entity_id\": \"$ENTITY\", \"effect\": \"$effect\"}" \
  "$HA_URL/api/services/light/turn_on"
echo ""
echo "Done. Check the Voice PE LED ring!"
echo ""
echo "Available effects:"
echo "  Progress 1-6  # Green progress LEDs"
echo "  Waiting       # Full orange ring"
echo "  Approved      # Full green ring"
echo "  Rejected      # Full red ring"
