#!/bin/bash
# Add a forward zone to MAAS DNS for fake TLDs (e.g., .homelab)
# Usage: ./02-add-forward-zone.sh <domain> [forwarder_ip]
set -e

DOMAIN="${1:?Usage: $0 <domain> [forwarder_ip]}"
FORWARDER_IP="${2:-192.168.4.1}"

PVE_HOST="pve.maas"
MAAS_VMID="102"
CONFIG_FILE="/var/snap/maas/current/bind/named.conf.local.maas"

echo "=== Adding Forward Zone for .${DOMAIN} ==="
echo "Forwarder: ${FORWARDER_IP}"
echo ""

# Get current snap revision (bind uses versioned path)
echo "1. Getting MAAS snap revision..."
SNAP_REV=$(ssh root@${PVE_HOST} "qm guest exec ${MAAS_VMID} -- bash -c 'readlink /var/snap/maas/current'" 2>/dev/null | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('out-data','').strip())")
echo "   Snap revision: ${SNAP_REV}"

NAMED_CONF="/var/snap/maas/${SNAP_REV}/bind/named.conf"

# Backup current config
echo ""
echo "2. Backing up named.conf..."
BACKUP_NAME="named.conf.bak.$(date +%Y%m%d-%H%M%S)"
ssh root@${PVE_HOST} "qm guest exec ${MAAS_VMID} -- cp ${NAMED_CONF} /var/snap/maas/${SNAP_REV}/bind/${BACKUP_NAME}"
echo "   Backup: /var/snap/maas/${SNAP_REV}/bind/${BACKUP_NAME}"

# Create or append to local config file
echo ""
echo "3. Creating forward zone configuration..."
ZONE_CONFIG="zone \\\"${DOMAIN}\\\" {
    type forward;
    forward only;
    forwarders { ${FORWARDER_IP}; };
};"

ssh root@${PVE_HOST} "qm guest exec ${MAAS_VMID} -- bash -c 'cat >> ${CONFIG_FILE} << EOF
zone \"${DOMAIN}\" {
    type forward;
    forward only;
    forwarders { ${FORWARDER_IP}; };
};
EOF
'"
echo "   Added zone to ${CONFIG_FILE}"

# Check if include exists in named.conf
echo ""
echo "4. Ensuring include directive exists..."
INCLUDE_EXISTS=$(ssh root@${PVE_HOST} "qm guest exec ${MAAS_VMID} -- grep -c 'named.conf.local.maas' ${NAMED_CONF} 2>/dev/null || echo '0'" 2>/dev/null | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('out-data','0').strip())")

if [[ "$INCLUDE_EXISTS" == "0" ]]; then
    echo "   Adding include directive to named.conf..."
    ssh root@${PVE_HOST} "qm guest exec ${MAAS_VMID} -- bash -c 'echo include \\\"${CONFIG_FILE}\\\"\; >> ${NAMED_CONF}'"
else
    echo "   Include directive already exists"
fi

# Restart bind
echo ""
echo "5. Restarting bind..."
ssh root@${PVE_HOST} "qm guest exec ${MAAS_VMID} -- pkill -9 named"
sleep 3

# Verify
echo ""
echo "6. Verifying..."
NEW_PID=$(ssh root@${PVE_HOST} "qm guest exec ${MAAS_VMID} -- pgrep named" 2>/dev/null | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('out-data','').strip())")
if [[ -n "$NEW_PID" ]]; then
    echo "   ✅ Bind restarted (PID: ${NEW_PID})"
else
    echo "   ❌ Bind failed to restart! Check config."
    exit 1
fi

# Test resolution
echo ""
echo "7. Testing resolution..."
TEST_RESULT=$(ssh root@${PVE_HOST} "qm guest exec ${MAAS_VMID} -- bash -c 'host test.${DOMAIN} 127.0.0.1 2>&1'" 2>/dev/null | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('out-data',''))")
echo "   $TEST_RESULT"

echo ""
echo "=== Done ==="
echo "Forward zone for .${DOMAIN} added to MAAS DNS"
echo "All .${DOMAIN} queries will now forward to ${FORWARDER_IP}"
