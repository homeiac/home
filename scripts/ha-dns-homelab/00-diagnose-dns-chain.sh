#!/bin/bash
# 00-diagnose-dns-chain.sh
# Diagnoses the full DNS chain for frigate.app.homelab
# Run this from Mac to check if DNS is working at each layer

set -euo pipefail

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

FRIGATE_HOSTNAME="frigate.app.homelab"
TRAEFIK_IP="192.168.4.80"
OPNSENSE_DNS="192.168.4.1"
MAAS_DNS="192.168.4.53"

echo "========================================="
echo "DNS Chain Diagnosis for $FRIGATE_HOSTNAME"
echo "========================================="
echo ""

# 1. Test Mac DNS resolution
echo "--- Step 1: Mac DNS Resolution ---"
MAC_RESULT=$(nslookup "$FRIGATE_HOSTNAME" 2>&1 || true)
if echo "$MAC_RESULT" | grep -q "$TRAEFIK_IP"; then
    echo -e "${GREEN}✓${NC} Mac resolves $FRIGATE_HOSTNAME -> $TRAEFIK_IP"
else
    echo -e "${RED}✗${NC} Mac DNS resolution failed"
    echo "  Output: $MAC_RESULT"
fi
echo ""

# 2. Test Traefik is responding
echo "--- Step 2: Traefik Responsiveness ---"
TRAEFIK_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 -H "Host: $FRIGATE_HOSTNAME" "http://$TRAEFIK_IP/" 2>&1 || echo "failed")
if [[ "$TRAEFIK_STATUS" == "200" ]] || [[ "$TRAEFIK_STATUS" == "301" ]] || [[ "$TRAEFIK_STATUS" == "302" ]]; then
    echo -e "${GREEN}✓${NC} Traefik ($TRAEFIK_IP) responds with HTTP $TRAEFIK_STATUS"
else
    echo -e "${RED}✗${NC} Traefik not responding (status: $TRAEFIK_STATUS)"
fi
echo ""

# 3. Query OPNsense DNS directly
echo "--- Step 3: OPNsense DNS ($OPNSENSE_DNS) ---"
OPNSENSE_RESULT=$(dig "$FRIGATE_HOSTNAME" @"$OPNSENSE_DNS" +short 2>&1 || true)
if [[ "$OPNSENSE_RESULT" == "$TRAEFIK_IP" ]]; then
    echo -e "${GREEN}✓${NC} OPNsense returns $FRIGATE_HOSTNAME -> $OPNSENSE_RESULT"
else
    echo -e "${YELLOW}⚠${NC} OPNsense returned: ${OPNSENSE_RESULT:-empty}"
    echo "  Expected: $TRAEFIK_IP"
fi
echo ""

# 4. Query MAAS DNS directly
echo "--- Step 4: MAAS DNS Forwarding ($MAAS_DNS) ---"
MAAS_RESULT=$(dig "$FRIGATE_HOSTNAME" @"$MAAS_DNS" +short 2>&1 || true)
if [[ "$MAAS_RESULT" == "$TRAEFIK_IP" ]]; then
    echo -e "${GREEN}✓${NC} MAAS forwards correctly: $FRIGATE_HOSTNAME -> $MAAS_RESULT"
else
    echo -e "${YELLOW}⚠${NC} MAAS returned: ${MAAS_RESULT:-empty}"
    echo "  Expected: $TRAEFIK_IP (forwarded via OPNsense)"
    echo "  This may indicate MAAS DNS forwarding is not working"
fi
echo ""

# 5. Direct Frigate access test
echo "--- Step 5: Direct Frigate Access via Traefik ---"
FRIGATE_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "http://$FRIGATE_HOSTNAME/" 2>&1 || echo "failed")
if [[ "$FRIGATE_STATUS" == "200" ]]; then
    echo -e "${GREEN}✓${NC} http://$FRIGATE_HOSTNAME/ returns HTTP 200"
else
    echo -e "${YELLOW}⚠${NC} http://$FRIGATE_HOSTNAME/ status: $FRIGATE_STATUS"
fi
echo ""

# Summary
echo "========================================="
echo "Diagnosis Complete"
echo "========================================="
echo ""
echo "If all checks pass from Mac but HA still fails:"
echo "  -> HA is using a different DNS server"
echo "  -> Run ./01-test-ha-can-reach-frigate.sh to confirm"
echo "  -> Then use Option B or C to fix"
