#!/bin/bash
# Check ESPHome addon status via chief-horse (direct access to HA)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

if [[ -z "$HA_TOKEN" ]]; then
    echo "ERROR: HA_TOKEN not found"
    exit 1
fi

echo "=== ESPHome Addon Check (via chief-horse) ==="
echo ""

echo "1. Listing all addons..."
ssh root@chief-horse.maas "curl -s --max-time 10 -H 'Authorization: Bearer $HA_TOKEN' 'http://192.168.4.240:8123/api/hassio/addons'" 2>/dev/null | jq -r '.data.addons[] | "\(.name): \(.state)"'

echo ""
echo "2. Checking specifically for ESPHome..."
ESPHOME_STATUS=$(ssh root@chief-horse.maas "curl -s --max-time 10 -H 'Authorization: Bearer $HA_TOKEN' 'http://192.168.4.240:8123/api/hassio/addons'" 2>/dev/null | jq -r '.data.addons[] | select(.slug | test("esphome"; "i")) | "\(.name): \(.state)"')

if [[ -n "$ESPHOME_STATUS" ]]; then
    echo "   $ESPHOME_STATUS"
else
    echo "   ESPHome addon NOT INSTALLED"
    echo ""
    echo "   To install: HA UI → Settings → Add-ons → Add-on Store → ESPHome"
fi
