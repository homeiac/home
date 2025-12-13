#!/bin/bash
# 04-verify-frigate-app-homelab-works.sh
# End-to-end verification that frigate.app.homelab works
# Run after applying fix to confirm success

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

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

FRIGATE_HOSTNAME="frigate.app.homelab"
TRAEFIK_IP="192.168.4.80"
HA_URL="http://192.168.4.240:8123"

PASS=0
FAIL=0

check() {
    local name="$1"
    local result="$2"
    if [[ "$result" == "pass" ]]; then
        echo -e "${GREEN}✓${NC} $name"
        ((PASS++))
    else
        echo -e "${RED}✗${NC} $name"
        ((FAIL++))
    fi
}

echo "========================================="
echo "End-to-End Verification"
echo "========================================="
echo ""

# 1. DNS Resolution from Mac
echo "--- DNS Resolution ---"
MAC_IP=$(nslookup "$FRIGATE_HOSTNAME" 2>/dev/null | grep -A1 "Name:" | grep "Address" | awk '{print $2}' | head -1 || echo "")
if [[ "$MAC_IP" == "$TRAEFIK_IP" ]]; then
    check "Mac DNS: $FRIGATE_HOSTNAME -> $TRAEFIK_IP" "pass"
else
    check "Mac DNS: $FRIGATE_HOSTNAME -> $TRAEFIK_IP (got: $MAC_IP)" "fail"
fi

# 2. Traefik Routing
echo ""
echo "--- Traefik Routing ---"
TRAEFIK_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "http://$FRIGATE_HOSTNAME/" 2>&1 || echo "failed")
if [[ "$TRAEFIK_STATUS" == "200" ]]; then
    check "Traefik routes http://$FRIGATE_HOSTNAME/ (HTTP 200)" "pass"
else
    check "Traefik routes http://$FRIGATE_HOSTNAME/ (got: $TRAEFIK_STATUS)" "fail"
fi

# 3. Direct Traefik with Host header
DIRECT_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 -H "Host: $FRIGATE_HOSTNAME" "http://$TRAEFIK_IP/" 2>&1 || echo "failed")
if [[ "$DIRECT_STATUS" == "200" ]]; then
    check "Direct Traefik IP with Host header (HTTP 200)" "pass"
else
    check "Direct Traefik IP with Host header (got: $DIRECT_STATUS)" "fail"
fi

# 4. HA API accessible
echo ""
echo "--- Home Assistant ---"
HA_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 \
    -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/" 2>&1 || echo "failed")
if [[ "$HA_STATUS" == "200" ]] || [[ "$HA_STATUS" == "201" ]]; then
    check "HA API accessible at $HA_URL" "pass"
else
    check "HA API accessible (got: $HA_STATUS)" "fail"
fi

# 5. Check Frigate entities in HA
STATES=$(curl -s --max-time 10 \
    -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/states" 2>&1 || echo "[]")

FRIGATE_COUNT=$(echo "$STATES" | grep -c "frigate" || echo "0")
if [[ "$FRIGATE_COUNT" -gt 0 ]]; then
    check "Frigate entities in HA ($FRIGATE_COUNT found)" "pass"
else
    check "Frigate entities in HA (none found - may use different name)" "fail"
fi

# Summary
echo ""
echo "========================================="
echo "Summary: $PASS passed, $FAIL failed"
echo "========================================="
echo ""
if [[ $FAIL -eq 0 ]]; then
    echo -e "${GREEN}ALL CHECKS PASSED${NC}"
    echo "frigate.app.homelab is working correctly!"
    exit 0
else
    echo -e "${RED}SOME CHECKS FAILED${NC}"
    echo "Review the failed checks above."
    echo ""
    echo "If Mac DNS works but HA doesn't have Frigate entities:"
    echo "  -> Update Frigate integration URL in HA to use hostname"
    exit 1
fi
