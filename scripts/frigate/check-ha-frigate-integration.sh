#!/bin/bash
#
# check-ha-frigate-integration.sh
#
# Check current Frigate integration configuration in Home Assistant
# Shows which Frigate URL is configured and integration status
#

set -euo pipefail

# Load environment variables
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../proxmox/homelab/.env"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: Cannot find .env file at $ENV_FILE"
    exit 1
fi

# Load HA credentials (extract specific variables to avoid syntax errors)
HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2-)
HA_URL=$(grep "^HA_URL=" "$ENV_FILE" | cut -d'=' -f2-)

if [[ -z "$HA_TOKEN" ]] || [[ -z "$HA_URL" ]]; then
    echo "ERROR: HA_TOKEN or HA_URL not set in .env file"
    exit 1
fi

echo "========================================="
echo "Home Assistant Frigate Integration Check"
echo "========================================="
echo ""
echo "Home Assistant URL: $HA_URL"
echo ""

# Check HA API is accessible
echo "Checking Home Assistant API..."
if ! curl -sf -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/" > /dev/null; then
    echo "ERROR: Cannot access Home Assistant API"
    exit 1
fi
echo "✓ Home Assistant API is accessible"
echo ""

# Get Frigate integration config
echo "Checking Frigate integration configuration..."
echo ""

# Try to get integration details via states API (Frigate creates sensor entities)
FRIGATE_SENSORS=$(curl -sf -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/states" | \
    jq -r '.[] | select(.entity_id | startswith("sensor.frigate_")) | .entity_id' | head -5)

if [[ -n "$FRIGATE_SENSORS" ]]; then
    echo "✓ Frigate integration is active (found Frigate entities)"
    echo ""
    echo "Sample Frigate entities:"
    echo "$FRIGATE_SENSORS" | sed 's/^/  - /'
    echo ""
else
    echo "⚠ No Frigate entities found - integration may not be configured"
    echo ""
fi

# Try to get Frigate binary sensor (cameras)
FRIGATE_CAMERAS=$(curl -sf -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/states" | \
    jq -r '.[] | select(.entity_id | startswith("camera.")) | select(.attributes.attribution? == "Data provided by Frigate") | .entity_id')

if [[ -n "$FRIGATE_CAMERAS" ]]; then
    echo "✓ Frigate cameras found:"
    echo "$FRIGATE_CAMERAS" | sed 's/^/  - /'
    echo ""
else
    echo "⚠ No Frigate cameras found"
    echo ""
fi

# Get Frigate stats sensor to find URL
FRIGATE_STATS=$(curl -sf -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/states" | \
    jq -r '.[] | select(.entity_id == "sensor.frigate_stats")')

if [[ -n "$FRIGATE_STATS" ]]; then
    echo "Frigate stats sensor details:"
    echo "$FRIGATE_STATS" | jq '{
        entity_id: .entity_id,
        state: .state,
        last_updated: .last_updated,
        attributes: .attributes | {
            friendly_name: .friendly_name,
            attribution: .attribution
        }
    }'
    echo ""
fi

# Manual check instructions
echo "========================================="
echo "MANUAL CHECK INSTRUCTIONS"
echo "========================================="
echo ""
echo "To verify Frigate URL in Home Assistant UI:"
echo "1. Go to: Settings → Devices & Services → Integrations"
echo "2. Find 'Frigate' integration"
echo "3. Click 'Configure' to see the configured URL"
echo ""
echo "Expected URLs:"
echo "  OLD (LXC):  http://still-fawn.maas:5000 or http://192.168.4.17:5000"
echo "  NEW (K8s):  http://192.168.4.83:5000"
echo ""
echo "Note: The Frigate integration URL cannot be retrieved via API."
echo "      You must check it manually in the Home Assistant UI."
echo ""
