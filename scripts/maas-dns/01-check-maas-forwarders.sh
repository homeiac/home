#!/bin/bash
# Check MAAS DNS forwarder configuration
# Usage: ./01-check-maas-forwarders.sh
set -e

PVE_HOST="pve.maas"
MAAS_VMID="102"

echo "=== MAAS DNS Forwarder Configuration ==="
echo ""

echo "1. Checking MAAS upstream DNS setting (from UI)..."
ssh root@${PVE_HOST} "qm guest exec ${MAAS_VMID} -- cat /var/snap/maas/current/bind/named.conf.options.inside.maas" 2>/dev/null | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('out-data',''))" | grep -A5 "forwarders"
echo ""

echo "2. Checking for custom forward zones..."
FORWARD_ZONES=$(ssh root@${PVE_HOST} "qm guest exec ${MAAS_VMID} -- bash -c 'cat /var/snap/maas/current/bind/named.conf.local.maas 2>/dev/null || echo NOT_FOUND'" 2>/dev/null | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('out-data',''))")
if [[ "$FORWARD_ZONES" == "NOT_FOUND" || -z "$FORWARD_ZONES" ]]; then
    echo "   ⚠️  No custom forward zones configured"
    echo "   → .homelab and other fake TLDs won't forward properly"
else
    echo "   Custom forward zones:"
    echo "$FORWARD_ZONES"
fi
echo ""

echo "3. Checking if bind is running..."
BIND_PID=$(ssh root@${PVE_HOST} "qm guest exec ${MAAS_VMID} -- pgrep named" 2>/dev/null | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('out-data','').strip())")
if [[ -n "$BIND_PID" ]]; then
    echo "   ✅ Bind is running (PID: ${BIND_PID})"
else
    echo "   ❌ Bind is NOT running!"
fi
echo ""

echo "4. Testing forwarding from inside MAAS VM..."
echo "   Testing google.com (should forward to upstream)..."
GOOGLE_TEST=$(ssh root@${PVE_HOST} "qm guest exec ${MAAS_VMID} -- bash -c 'host google.com 127.0.0.1 2>&1'" 2>/dev/null | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('out-data',''))" | grep -o "has address" || echo "FAILED")
if [[ "$GOOGLE_TEST" == "has address" ]]; then
    echo "   ✅ General forwarding works"
else
    echo "   ❌ General forwarding broken"
fi

echo "   Testing rancher.homelab (fake TLD)..."
HOMELAB_TEST=$(ssh root@${PVE_HOST} "qm guest exec ${MAAS_VMID} -- bash -c 'host rancher.homelab 127.0.0.1 2>&1'" 2>/dev/null | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('out-data',''))" | grep -o "has address" || echo "FAILED")
if [[ "$HOMELAB_TEST" == "has address" ]]; then
    echo "   ✅ .homelab forwarding works"
else
    echo "   ❌ .homelab forwarding NOT working"
    echo "   → Run: ./02-add-forward-zone.sh homelab"
fi
