#!/bin/bash
# Check light state
# Usage: ./check-light-state.sh [entity_id]

set -e

# Default to Monitor light
LIGHT_ENTITY="${1:-light.smart_dimmer_switch_2005093382991125581748e1e91baafc}"

# Load HA token
HA_TOKEN=$(grep "^HA_TOKEN=" ~/code/home/proxmox/homelab/.env | cut -d'=' -f2 | tr -d '"')
HA_URL="${HA_URL:-http://192.168.4.240:8123}"

echo "=== Light State: $LIGHT_ENTITY ==="
curl -s -H "Authorization: Bearer $HA_TOKEN" \
  "$HA_URL/api/states/$LIGHT_ENTITY" | jq '{
    entity_id,
    state,
    brightness: .attributes.brightness,
    friendly_name: .attributes.friendly_name,
    last_changed
  }'
