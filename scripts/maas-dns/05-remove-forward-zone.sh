#!/bin/bash
# Remove a forward zone from MAAS DNS
# Usage: ./05-remove-forward-zone.sh <domain>
set -e

DOMAIN="${1:?Usage: $0 <domain>}"

PVE_HOST="pve.maas"
MAAS_VMID="102"
CONFIG_FILE="/var/snap/maas/current/bind/named.conf.local.maas"

echo "=== Removing Forward Zone for .${DOMAIN} ==="
echo ""

# Check if zone exists
echo "1. Checking if zone exists..."
ZONE_EXISTS=$(ssh root@${PVE_HOST} "qm guest exec ${MAAS_VMID} -- grep -c 'zone \"${DOMAIN}\"' ${CONFIG_FILE} 2>/dev/null || echo '0'" 2>/dev/null | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('out-data','0').strip())")

if [[ "$ZONE_EXISTS" == "0" ]]; then
    echo "   Zone .${DOMAIN} not found in config"
    exit 0
fi

# Backup
echo ""
echo "2. Backing up config..."
BACKUP_NAME="named.conf.local.maas.bak.$(date +%Y%m%d-%H%M%S)"
ssh root@${PVE_HOST} "qm guest exec ${MAAS_VMID} -- cp ${CONFIG_FILE} /var/snap/maas/current/bind/${BACKUP_NAME}"
echo "   Backup: ${BACKUP_NAME}"

# Remove zone block (sed delete from zone line to next };)
echo ""
echo "3. Removing zone block..."
ssh root@${PVE_HOST} "qm guest exec ${MAAS_VMID} -- bash -c 'sed -i \"/^zone \\\"${DOMAIN}\\\"/,/^};/d\" ${CONFIG_FILE}'"

# Restart bind
echo ""
echo "4. Restarting bind..."
ssh root@${PVE_HOST} "qm guest exec ${MAAS_VMID} -- pkill -9 named"
sleep 3

echo ""
echo "5. Verifying..."
NEW_PID=$(ssh root@${PVE_HOST} "qm guest exec ${MAAS_VMID} -- pgrep named" 2>/dev/null | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('out-data','').strip())")
if [[ -n "$NEW_PID" ]]; then
    echo "   ✅ Bind restarted (PID: ${NEW_PID})"
else
    echo "   ❌ Bind failed to restart!"
    exit 1
fi

echo ""
echo "=== Done ==="
echo "Forward zone for .${DOMAIN} removed"
