#!/bin/bash
# Find where ESPHome stores its config on HAOS
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

echo "=== Finding ESPHome Config Location ==="
echo ""

echo "1. ESPHome addon info:"
curl -s --max-time 15 -H "Authorization: Bearer $HA_TOKEN" \
    "http://192.168.1.122:8123/api/hassio/addons/5c53de3b_esphome/info" 2>/dev/null | jq '.data | {name, state, version, options}' || echo "   Could not query addon API"

echo ""
echo "2. Looking for compiling processes on HAOS:"
ssh root@chief-horse.maas "qm guest exec 116 -- ps aux" 2>/dev/null | jq -r '."out-data"' | grep -iE "esphome|platformio|xtensa|compile" | head -10 || echo "   No compile processes visible"

echo ""
echo "3. ESPHome device list via API:"
curl -s --max-time 15 -H "Authorization: Bearer $HA_TOKEN" \
    "http://192.168.1.122:8123/api/hassio/addons/5c53de3b_esphome/stdin" 2>/dev/null || echo "   stdin API not available"

echo ""
echo "4. Check ESPHome dashboard entries:"
# The dashboard stores device info - try the websocket info endpoint
curl -s --max-time 15 -H "Authorization: Bearer $HA_TOKEN" \
    "http://192.168.1.122:8123/api/hassio/ingress/5c53de3b_esphome" 2>/dev/null | head -c 500 || echo "   Ingress API blocked"
