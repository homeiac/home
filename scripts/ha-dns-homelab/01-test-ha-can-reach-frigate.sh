#!/bin/bash
# 01-test-ha-can-reach-frigate.sh
# Tests if Home Assistant can reach Frigate via hostname and direct IP
# Uses HA API to check Frigate integration status

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../../proxmox/homelab/.env"

# Load HA_TOKEN from .env
if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2 | tr -d '"')
else
    echo "ERROR: .env file not found at $ENV_FILE"
    echo "Please ensure HA_TOKEN is set in proxmox/homelab/.env"
    exit 1
fi

if [[ -z "$HA_TOKEN" ]]; then
    echo "ERROR: HA_TOKEN not found in .env"
    exit 1
fi

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

HA_URL="http://192.168.4.240:8123"
FRIGATE_HOSTNAME="frigate.app.homelab"
TRAEFIK_IP="192.168.4.80"

echo "========================================="
echo "Testing Home Assistant -> Frigate Access"
echo "========================================="
echo ""

# 1. Test HA API is accessible
echo "--- Step 1: HA API Accessibility ---"
HA_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 \
    -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/" 2>&1 || echo "failed")
if [[ "$HA_STATUS" == "200" ]] || [[ "$HA_STATUS" == "201" ]]; then
    echo -e "${GREEN}✓${NC} HA API accessible at $HA_URL"
else
    echo -e "${RED}✗${NC} HA API not accessible (status: $HA_STATUS)"
    echo "  Cannot proceed with further tests"
    exit 1
fi
echo ""

# 2. Check Frigate integration status
echo "--- Step 2: Frigate Integration Status ---"
INTEGRATIONS=$(curl -s --max-time 10 \
    -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/config/config_entries/entry" 2>&1 || echo "[]")

if echo "$INTEGRATIONS" | grep -qi "frigate"; then
    echo -e "${GREEN}✓${NC} Frigate integration found in HA"
    # Try to get more details
    FRIGATE_ENTRY=$(echo "$INTEGRATIONS" | grep -i frigate | head -1 || true)
    if [[ -n "$FRIGATE_ENTRY" ]]; then
        echo "  Integration details available"
    fi
else
    echo -e "${YELLOW}⚠${NC} Frigate integration not found or not configured"
    echo "  This is expected if Frigate integration uses direct IP"
fi
echo ""

# 3. Check HA states for Frigate entities
echo "--- Step 3: Frigate Entities in HA ---"
STATES=$(curl -s --max-time 10 \
    -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/states" 2>&1 || echo "[]")

FRIGATE_ENTITIES=$(echo "$STATES" | grep -c "frigate" || echo "0")
if [[ "$FRIGATE_ENTITIES" -gt 0 ]]; then
    echo -e "${GREEN}✓${NC} Found $FRIGATE_ENTITIES Frigate-related entities in HA"
else
    echo -e "${YELLOW}⚠${NC} No Frigate entities found in HA states"
fi
echo ""

# Summary
echo "========================================="
echo "Test Complete"
echo "========================================="
echo ""
echo "If HA has Frigate integration but uses IP instead of hostname:"
echo "  -> Update Frigate integration URL to use $FRIGATE_HOSTNAME"
echo "  -> First ensure DNS works (run ./00-diagnose-dns-chain.sh)"
echo ""
echo "If DNS works from Mac but not from HA:"
echo "  -> Run ./02-print-opnsense-dns-fix-steps.sh (Option B)"
echo "  -> Or run ./03-print-ha-nmcli-fix-commands.sh (Option C)"
