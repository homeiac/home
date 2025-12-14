#!/bin/bash
# List all Frigate entities in Home Assistant
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

[[ -z "$HA_TOKEN" ]] && { echo "ERROR: HA_TOKEN not found"; exit 1; }

HA_URL="${HA_URL:-http://192.168.4.240:8123}"

echo "=== Frigate Entities in Home Assistant ==="
echo ""

curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/states" | \
    jq -r '.[] | select(.entity_id | contains("frigate")) | "\(.entity_id) = \(.state)"' | sort

echo ""
echo "=== Camera Entities ==="
curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/states" | \
    jq -r '.[] | select(.entity_id | startswith("camera.")) | "\(.entity_id)"' | sort
