#!/bin/bash
# Check Piper TTS addon configuration
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

HA_HOST="${HA_HOST:-homeassistant.maas}"

echo "=== Piper TTS Addon Configuration ==="
echo ""

# List all addons to find piper
echo "1. Finding Piper addon..."
PIPER_SLUG=$(curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "http://$HA_HOST:8123/api/hassio/addons" 2>/dev/null | \
    jq -r '.data.addons[] | select(.name | test("piper"; "i")) | .slug')

if [[ -z "$PIPER_SLUG" ]]; then
    echo "   Piper addon not found!"
    echo ""
    echo "   Available addons:"
    curl -s -H "Authorization: Bearer $HA_TOKEN" \
        "http://$HA_HOST:8123/api/hassio/addons" 2>/dev/null | \
        jq -r '.data.addons[] | "   - \(.name) (\(.slug))"'
    exit 1
fi

echo "   Found: $PIPER_SLUG"
echo ""

# Get addon info
echo "2. Addon status:"
curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "http://$HA_HOST:8123/api/hassio/addons/$PIPER_SLUG/info" 2>/dev/null | \
    jq '{name, version, state, cpu_percent, memory_percent, memory_limit}'
echo ""

# Get addon options (voice model config)
echo "3. Current voice configuration:"
curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "http://$HA_HOST:8123/api/hassio/addons/$PIPER_SLUG/info" 2>/dev/null | \
    jq '.data.options'
echo ""

echo "=== Voice Model Quality Levels ==="
echo "  - low:    Fastest, lowest quality"
echo "  - medium: Balanced (likely current)"
echo "  - high:   Slowest, best quality"
echo ""
echo "To change model, use: ./change-piper-model.sh <quality>"
