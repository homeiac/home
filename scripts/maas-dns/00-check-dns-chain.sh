#!/bin/bash
# Check full DNS resolution chain: Mac -> MAAS -> OPNsense
# Usage: ./00-check-dns-chain.sh [hostname] [domain]
set -e

HOSTNAME="${1:-rancher}"
DOMAIN="${2:-homelab}"
FQDN="${HOSTNAME}.${DOMAIN}"

MAAS_IP="192.168.4.53"
OPNSENSE_IP="192.168.4.1"
PVE_HOST="pve.maas"
MAAS_VMID="102"

echo "=== DNS Resolution Chain Check for ${FQDN} ==="
echo ""

echo "1. Testing OPNsense (${OPNSENSE_IP}) directly..."
OPNSENSE_RESULT=$(dig +short "${FQDN}" @${OPNSENSE_IP} 2>/dev/null || echo "FAILED")
if [[ -n "$OPNSENSE_RESULT" && "$OPNSENSE_RESULT" != "FAILED" ]]; then
    echo "   ✅ OPNsense: ${FQDN} -> ${OPNSENSE_RESULT}"
else
    echo "   ❌ OPNsense: NXDOMAIN or unreachable"
    echo "   → Add host override in OPNsense: Services → Unbound DNS → Overrides"
fi
echo ""

echo "2. Testing MAAS (${MAAS_IP}) directly..."
MAAS_RESULT=$(dig +short "${FQDN}" @${MAAS_IP} 2>/dev/null || echo "FAILED")
if [[ -n "$MAAS_RESULT" && "$MAAS_RESULT" != "FAILED" ]]; then
    echo "   ✅ MAAS: ${FQDN} -> ${MAAS_RESULT}"
else
    echo "   ❌ MAAS: NXDOMAIN or unreachable"
    echo "   → MAAS is not forwarding .${DOMAIN} to OPNsense"
    echo "   → Run: ./01-check-maas-forwarders.sh"
fi
echo ""

echo "3. Testing local resolver..."
LOCAL_RESULT=$(dig +short "${FQDN}" 2>/dev/null || echo "FAILED")
if [[ -n "$LOCAL_RESULT" && "$LOCAL_RESULT" != "FAILED" ]]; then
    echo "   ✅ Local: ${FQDN} -> ${LOCAL_RESULT}"
else
    echo "   ❌ Local resolver failed"
    echo "   → Check /etc/resolv.conf or macOS DNS settings"
fi
echo ""

echo "=== Summary ==="
if [[ -n "$MAAS_RESULT" && "$MAAS_RESULT" != "FAILED" ]]; then
    echo "✅ DNS chain working: Mac -> MAAS -> OPNsense"
elif [[ -n "$OPNSENSE_RESULT" && "$OPNSENSE_RESULT" != "FAILED" ]]; then
    echo "⚠️  OPNsense has the record, but MAAS isn't forwarding"
    echo "   Run: ./02-add-forward-zone.sh ${DOMAIN}"
else
    echo "❌ Record not found anywhere"
    echo "   Add host override in OPNsense first"
fi
