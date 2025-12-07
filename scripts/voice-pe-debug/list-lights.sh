#!/bin/bash
# List all lights with friendly names

set -e

# Load HA token
HA_TOKEN=$(grep "^HA_TOKEN=" ~/code/home/proxmox/homelab/.env | cut -d'=' -f2 | tr -d '"')
HA_URL="${HA_URL:-http://192.168.4.240:8123}"

echo "=== All Lights ==="
curl -s -H "Authorization: Bearer $HA_TOKEN" \
  "$HA_URL/api/states" | \
  jq '.[] | select(.entity_id | startswith("light.")) | select(.entity_id | contains("dnd") | not) | {entity_id, friendly_name: .attributes.friendly_name, state}'
