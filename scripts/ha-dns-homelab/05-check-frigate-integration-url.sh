#!/bin/bash
# 05-check-frigate-integration-url.sh
# Checks what URL the Frigate integration is configured with in Home Assistant
# This reveals if HA is using IP or hostname for Frigate

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../../proxmox/homelab/.env"

# Load HA_TOKEN from .env
if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2 | tr -d '"')
else
    echo "ERROR: .env file not found at $ENV_FILE"
    exit 1
fi

if [[ -z "$HA_TOKEN" ]]; then
    echo "ERROR: HA_TOKEN not found in .env"
    exit 1
fi

HA_URL="http://192.168.4.240:8123"

echo "========================================="
echo "Checking Frigate Integration Configuration"
echo "========================================="
echo ""

# Get all config entries
echo "--- Frigate Integration Entry ---"
FRIGATE_CONFIG=$(curl -s --max-time 10 \
    -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/config/config_entries/entry" 2>/dev/null | jq -r '.[] | select(.domain == "frigate")' 2>/dev/null || echo "{}")

if [[ -z "$FRIGATE_CONFIG" ]] || [[ "$FRIGATE_CONFIG" == "{}" ]]; then
    echo "No Frigate integration found in HA config entries"
    echo ""
    echo "Checking for frigate in states instead..."

    # Check states for frigate URL hints
    FRIGATE_STATES=$(curl -s --max-time 10 \
        -H "Authorization: Bearer $HA_TOKEN" \
        "$HA_URL/api/states" 2>/dev/null | jq -r '.[] | select(.entity_id | contains("frigate"))' 2>/dev/null | head -50 || echo "")

    if [[ -n "$FRIGATE_STATES" ]]; then
        echo "Found Frigate entities:"
        echo "$FRIGATE_STATES" | jq -r '.entity_id' 2>/dev/null | head -10
    fi
else
    echo "Frigate integration found:"
    echo "$FRIGATE_CONFIG" | jq '.' 2>/dev/null || echo "$FRIGATE_CONFIG"
    echo ""

    # Extract URL if present
    FRIGATE_URL=$(echo "$FRIGATE_CONFIG" | jq -r '.data.url // .data.host // "not found"' 2>/dev/null)
    echo "--- Configured URL ---"
    echo "URL: $FRIGATE_URL"
    echo ""

    if [[ "$FRIGATE_URL" == *"192.168"* ]]; then
        echo "⚠️  Frigate is configured with IP address, not hostname"
        echo "   To use frigate.app.homelab, reconfigure the integration"
    elif [[ "$FRIGATE_URL" == *"frigate.app.homelab"* ]]; then
        echo "✓ Frigate is configured with hostname (frigate.app.homelab)"
    else
        echo "URL format: $FRIGATE_URL"
    fi
fi

echo ""
echo "========================================="
echo "To update Frigate integration URL:"
echo "  1. Go to HA Settings -> Devices & Services"
echo "  2. Find Frigate integration"
echo "  3. Click Configure"
echo "  4. Update URL to: http://frigate.app.homelab:5000"
echo "========================================="
