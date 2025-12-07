#!/bin/bash
# Check which pipeline Voice PE is using

set -e

# Load HA token
HA_TOKEN=$(grep "^HA_TOKEN=" ~/code/home/proxmox/homelab/.env | cut -d'=' -f2 | tr -d '"')
HA_URL="${HA_URL:-http://192.168.4.240:8123}"

echo "=== Voice PE Pipeline Assignment ==="
curl -s -H "Authorization: Bearer $HA_TOKEN" \
  "$HA_URL/api/states/select.home_assistant_voice_09f5a3_assistant" | jq '{
    current_pipeline: .state,
    available_options: .attributes.options
  }'
