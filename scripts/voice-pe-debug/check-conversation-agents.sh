#!/bin/bash
# Check conversation agent capabilities
# supported_features: 0 = chat only, 1 = can control devices

set -e

# Load HA token
HA_TOKEN=$(grep "^HA_TOKEN=" ~/code/home/proxmox/homelab/.env | cut -d'=' -f2 | tr -d '"')
HA_URL="${HA_URL:-http://192.168.4.240:8123}"

echo "=== Conversation Agents ==="
curl -s -H "Authorization: Bearer $HA_TOKEN" \
  "$HA_URL/api/states" | \
  jq '.[] | select(.entity_id | startswith("conversation.")) | {entity_id, friendly_name: .attributes.friendly_name, supported_features: .attributes.supported_features}'

echo ""
echo "Note: supported_features: 0 = chat only, 1 = can control devices"
