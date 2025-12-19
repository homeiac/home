#!/bin/bash
# List all forward zones configured in MAAS DNS
# Usage: ./03-list-forward-zones.sh
set -e

PVE_HOST="pve.maas"
MAAS_VMID="102"

echo "=== MAAS DNS Forward Zones ==="
echo ""

echo "Custom forward zones (named.conf.local.maas):"
ZONES=$(ssh root@${PVE_HOST} "qm guest exec ${MAAS_VMID} -- cat /var/snap/maas/current/bind/named.conf.local.maas 2>/dev/null" 2>/dev/null | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('out-data',''))" 2>/dev/null || echo "")

if [[ -z "$ZONES" ]]; then
    echo "   (none configured)"
else
    echo "$ZONES"
fi

echo ""
echo "Global forwarders (from MAAS UI):"
ssh root@${PVE_HOST} "qm guest exec ${MAAS_VMID} -- cat /var/snap/maas/current/bind/named.conf.options.inside.maas" 2>/dev/null | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('out-data',''))" | grep -A10 "^forwarders"
