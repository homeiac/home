#!/bin/bash
# Pre-flight check for Home Assistant debugging
# Run this BEFORE deep-diving into backend investigation
#
# This script checks for common issues that are often client-side or environmental,
# saving time before going down rabbit holes.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/.env" 2>/dev/null || true

HA_URL="${HA_URL:-http://homeassistant.maas:8123}"
HA_TOKEN="${HA_TOKEN:-}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=============================================="
echo "  Home Assistant Pre-Flight Debugging Check"
echo "=============================================="
echo ""

# Check 1: Is HA reachable?
echo -n "[1/6] Home Assistant API reachable... "
if curl -s --max-time 5 -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/" | grep -q "API running"; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC}"
    echo "      HA might be updating, restarting, or unreachable"
    echo "      → Wait and retry, or check network connectivity"
    exit 1
fi

# Check 2: HA Version and state
echo -n "[2/6] Home Assistant state... "
HA_STATE=$(curl -s --max-time 5 -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/config" | jq -r '.state')
HA_VERSION=$(curl -s --max-time 5 -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/config" | jq -r '.version')
if [ "$HA_STATE" = "RUNNING" ]; then
    echo -e "${GREEN}$HA_STATE${NC} (v$HA_VERSION)"
else
    echo -e "${YELLOW}$HA_STATE${NC} (v$HA_VERSION)"
    echo "      → HA may be starting up or in maintenance mode"
fi

# Check 3: Any failed integrations?
echo -n "[3/6] Failed integrations... "
FAILED=$(curl -s --max-time 10 -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/config/config_entries/entry" | \
    jq '[.[] | select(.state == "setup_error" or .state == "setup_retry" or .state == "failed_unload")] | length')
if [ "$FAILED" = "0" ]; then
    echo -e "${GREEN}None${NC}"
else
    echo -e "${YELLOW}$FAILED failed${NC}"
    curl -s --max-time 10 -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/config/config_entries/entry" | \
        jq -r '.[] | select(.state == "setup_error" or .state == "setup_retry" or .state == "failed_unload") | "      → \(.domain): \(.title) (\(.state))"'
fi

# Check 4: LLM Vision specifically
echo -n "[4/6] LLM Vision integration... "
LLMVISION_STATE=$(curl -s --max-time 10 -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/config/config_entries/entry" | \
    jq -r '[.[] | select(.domain == "llmvision")] | .[0].state // "not_found"')
if [ "$LLMVISION_STATE" = "loaded" ]; then
    PROVIDER_COUNT=$(curl -s --max-time 10 -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/config/config_entries/entry" | \
        jq '[.[] | select(.domain == "llmvision")] | length')
    echo -e "${GREEN}OK${NC} ($PROVIDER_COUNT providers)"
else
    echo -e "${RED}$LLMVISION_STATE${NC}"
fi

# Check 5: Test LLM Vision service call
echo -n "[5/6] LLM Vision service call... "
# Only test if we have a test image
if curl -s --max-time 30 -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    -d '{"provider": "01K1KDVH6Y1GMJ69MJF77WGJEA", "model": "llava:7b", "image_file": "/config/www/tmp/doorbell_after.jpg", "message": "test", "max_tokens": 5}' \
    "$HA_URL/api/services/llmvision/image_analyzer?return_response" 2>/dev/null | grep -q "response_text"; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${YELLOW}SKIPPED${NC} (no test image or service error)"
fi

# Check 6: Common client-side issues reminder
echo -n "[6/6] Client-side checklist... "
echo -e "${YELLOW}MANUAL CHECK REQUIRED${NC}"
echo ""
echo "      ┌─────────────────────────────────────────────────────────────┐"
echo "      │  BEFORE DEEP INVESTIGATION, CHECK THESE CLIENT-SIDE ISSUES: │"
echo "      ├─────────────────────────────────────────────────────────────┤"
echo "      │  □ Browser extensions blocking JavaScript (uBlock, NoScript)│"
echo "      │    → Common blocked domains: unpkg.com, jsdelivr.net, cdnjs │"
echo "      │  □ Browser cache (try Ctrl+Shift+R or incognito mode)       │"
echo "      │  □ Multiple browser tabs with HA open (can cause conflicts) │"
echo "      │  □ VPN or proxy interfering with WebSocket connections      │"
echo "      │  □ Browser console errors (F12 → Console tab)               │"
echo "      │  □ Different browser works? (Chrome vs Firefox vs Safari)   │"
echo "      └─────────────────────────────────────────────────────────────┘"
echo ""
echo "      If UI shows error but API calls above succeeded:"
echo "      → Problem is likely CLIENT-SIDE, not Home Assistant"
echo ""
echo "=============================================="
echo "  Pre-flight check complete"
echo "=============================================="
