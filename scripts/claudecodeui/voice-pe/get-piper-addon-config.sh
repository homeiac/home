#!/bin/bash
# Get Piper addon configuration (voice model settings)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

HA_HOST="${HA_HOST:-homeassistant.maas}"

echo "=== Piper Addon Configuration ==="

# List all addons first
echo "1. Finding Piper addon slug..."
ADDONS=$(curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "http://$HA_HOST:8123/api/hassio/addons" 2>/dev/null)

# Check if we got data
if echo "$ADDONS" | jq -e '.data.addons' > /dev/null 2>&1; then
    echo "$ADDONS" | jq -r '.data.addons[] | select(.name | test("piper"; "i")) | "   Found: \(.name) (\(.slug)) - \(.state)"'
    PIPER_SLUG=$(echo "$ADDONS" | jq -r '.data.addons[] | select(.name | test("piper"; "i")) | .slug')
else
    echo "   No addons returned. Checking supervisor API..."
    # Try supervisor endpoint
    curl -s -H "Authorization: Bearer $HA_TOKEN" \
        "http://$HA_HOST:8123/api/hassio/supervisor/info" | jq '.data.addons[] | select(.name | test("piper"; "i"))'
    exit 1
fi

if [[ -z "$PIPER_SLUG" ]]; then
    echo "   Piper addon not found!"
    echo ""
    echo "   Piper may be running as a Docker container, not an addon."
    echo "   Check: Settings → Add-ons in HA UI"
    exit 1
fi

echo ""
echo "2. Addon info:"
curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "http://$HA_HOST:8123/api/hassio/addons/$PIPER_SLUG/info" | jq '{
        name: .data.name,
        version: .data.version,
        state: .data.state,
        options: .data.options
    }'
