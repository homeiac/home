#!/bin/bash
# EMERGENCY: Restore MAAS DNS when .maas resolution is broken
# Usage: ./07-emergency-restore-maas-dns.sh
#
# ⚠️  USE THIS ONLY WHEN .maas DNS IS BROKEN ⚠️
# This does a full MAAS restart which regenerates zone files
set -e

PVE_HOST="pve.maas"
MAAS_VMID="102"

echo "=============================================="
echo "⚠️  EMERGENCY MAAS DNS RESTORE ⚠️"
echo "=============================================="
echo ""
echo "This will restart MAAS to regenerate DNS zone files."
echo "Only use this when .maas resolution is broken!"
echo ""

read -p "Are you sure? (yes/no): " confirm
if [[ "$confirm" != "yes" ]]; then
    echo "Aborted."
    exit 1
fi

echo ""
echo "1. Restarting MAAS (this takes ~15 seconds)..."
ssh root@${PVE_HOST} "qm guest exec ${MAAS_VMID} -- snap restart maas"

echo ""
echo "2. Waiting for DNS to come back up..."
sleep 15

echo ""
echo "3. Testing .maas resolution..."
RESULT=$(dig @192.168.4.53 still-fawn.maas +short 2>/dev/null || echo "FAILED")

if [[ -n "$RESULT" && "$RESULT" != "FAILED" ]]; then
    echo "   ✅ still-fawn.maas -> ${RESULT}"
    echo ""
    echo "MAAS DNS restored successfully."
else
    echo "   ❌ still-fawn.maas failed to resolve"
    echo ""
    echo "DNS still broken. Check MAAS VM status:"
    echo "  ssh root@${PVE_HOST} 'qm guest exec ${MAAS_VMID} -- snap services maas'"
fi
