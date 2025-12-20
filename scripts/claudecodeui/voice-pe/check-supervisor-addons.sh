#!/bin/bash
# Check supervisor addons via different API paths
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

HA_HOST="${HA_HOST:-homeassistant.maas}"

echo "=== Checking Supervisor Addons ==="

echo "1. /api/hassio/addons:"
curl -s -H "Authorization: Bearer $HA_TOKEN" "http://$HA_HOST:8123/api/hassio/addons" | head -c 500
echo ""
echo ""

echo "2. /api/hassio/supervisor/info:"
curl -s -H "Authorization: Bearer $HA_TOKEN" "http://$HA_HOST:8123/api/hassio/supervisor/info" | jq '.data.addons // "no addons key"' 2>/dev/null | head -20
echo ""

echo "3. /api/hassio/store:"
curl -s -H "Authorization: Bearer $HA_TOKEN" "http://$HA_HOST:8123/api/hassio/store" | jq 'keys' 2>/dev/null || echo "failed"
echo ""

echo "4. Check for piper specifically:"
# Try known piper addon slugs
for slug in "core_piper" "piper" "47701997_piper" "a]_piper"; do
    echo "   Trying: $slug"
    RESULT=$(curl -s -H "Authorization: Bearer $HA_TOKEN" "http://$HA_HOST:8123/api/hassio/addons/$slug/info" 2>/dev/null)
    if echo "$RESULT" | jq -e '.data.name' > /dev/null 2>&1; then
        echo "   FOUND!"
        echo "$RESULT" | jq '{name: .data.name, state: .data.state, options: .data.options}'
        exit 0
    fi
done
echo "   No known piper addon slug worked"
