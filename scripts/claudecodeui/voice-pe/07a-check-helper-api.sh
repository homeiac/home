#!/bin/bash
# Check HA API endpoint for input_boolean creation
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

echo "=== Checking HA Helper APIs ==="
echo ""

# Check config endpoint
echo "1. Testing /api/config/input_boolean (GET):"
curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "http://$HA_HOST:8123/api/config/input_boolean" | head -200

echo ""
echo ""

# Check if entity already exists
echo "2. Checking if entity exists:"
curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "http://$HA_HOST:8123/api/states/input_boolean.claude_awaiting_approval"

echo ""
echo ""

# List existing input_booleans
echo "3. Existing input_boolean entities:"
curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "http://$HA_HOST:8123/api/states" | jq '[.[] | select(.entity_id | startswith("input_boolean."))] | .[].entity_id'
