#!/bin/bash
# Check if ESPHome add-on is installed and get access URL
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

if [[ -z "$HA_TOKEN" ]]; then
    echo "ERROR: HA_TOKEN not found"
    exit 1
fi

HA_HOST="${HA_HOST:-homeassistant.maas}"

echo "=== Checking ESPHome Add-on ==="
echo ""

# Check supervisor add-ons
echo "Querying installed add-ons..."
ADDONS=$(curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "http://$HA_HOST:8123/api/hassio/addons" 2>/dev/null)

if echo "$ADDONS" | jq -e '.data.addons' > /dev/null 2>&1; then
    echo ""
    echo "ESPHome add-on status:"
    echo "$ADDONS" | jq -r '.data.addons[] | select(.slug | contains("esphome")) | "  Name: \(.name)\n  Slug: \(.slug)\n  State: \(.state)\n  Version: \(.version)"'

    ESPHOME_SLUG=$(echo "$ADDONS" | jq -r '.data.addons[] | select(.slug | contains("esphome")) | .slug' | head -1)

    if [[ -n "$ESPHOME_SLUG" ]]; then
        echo ""
        echo "Access ESPHome via:"
        echo "  1. HA Sidebar → ESPHome"
        echo "  2. http://$HA_HOST:8123/hassio/ingress/$ESPHOME_SLUG"
        echo "  3. Settings → Add-ons → ESPHome → OPEN WEB UI"
    else
        echo ""
        echo "⚠️  ESPHome add-on not found!"
        echo "Install via: Settings → Add-ons → Add-on Store → ESPHome"
    fi
else
    echo "Could not query add-ons (may need Supervisor API access)"
    echo ""
    echo "Try accessing ESPHome directly:"
    echo "  - HA UI: Sidebar → ESPHome (if installed)"
    echo "  - Settings → Add-ons → ESPHome"
fi
