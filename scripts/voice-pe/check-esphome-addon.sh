#!/bin/bash
# Check ESPHome addon status and Voice PE adoption
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

HA_URL="http://192.168.1.122:8123"

echo "=== ESPHome Addon Status ==="
echo ""

# List all addons, filter for esphome
echo "1. Checking for ESPHome addon..."
ADDONS=$(curl -s --max-time 10 -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/hassio/addons" 2>/dev/null)

if [[ -z "$ADDONS" ]]; then
    echo "   ERROR: Could not reach Hassio API"
    exit 1
fi

ESPHOME=$(echo "$ADDONS" | jq -r '.data.addons[] | select(.slug | test("esphome"; "i")) | "\(.name) (\(.slug)): \(.state)"')

if [[ -z "$ESPHOME" ]]; then
    echo "   ESPHome addon NOT INSTALLED"
    echo ""
    echo "   To install: Settings → Add-ons → Add-on Store → ESPHome"
else
    echo "   $ESPHOME"
fi

echo ""
echo "2. Checking Voice PE ESPHome entity..."
VOICE_PE=$(curl -s --max-time 10 -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/states" 2>/dev/null | \
    jq -r '.[] | select(.entity_id | test("voice.*pe|voice.*09f5a3"; "i")) | "\(.entity_id): \(.state)"' | head -5)

if [[ -n "$VOICE_PE" ]]; then
    echo "$VOICE_PE"
else
    echo "   No Voice PE entities found"
fi

echo ""
echo "3. Voice PE adoption options:"
echo "   a) OTA adoption: ESPHome dashboard can adopt devices on the network"
echo "   b) USB adoption: Connect USB-C cable and flash directly"
echo ""
echo "   To adopt OTA:"
echo "   1. Open ESPHome dashboard (HA sidebar → ESPHome)"
echo "   2. Click '+ NEW DEVICE'"
echo "   3. Select 'Home Assistant Voice PE'"
echo "   4. Follow the adoption wizard"
echo ""
echo "   After adoption, add to the device YAML:"
echo "   wifi:"
echo "     power_save_mode: none"
echo "     fast_connect: true"
