#!/bin/bash
# Restart MAAS bind DNS server
# Usage: ./04-restart-maas-bind.sh
set -e

PVE_HOST="pve.maas"
MAAS_VMID="102"

echo "=== Restarting MAAS Bind DNS ==="
echo ""

echo "1. Getting current bind PID..."
OLD_PID=$(ssh root@${PVE_HOST} "qm guest exec ${MAAS_VMID} -- pgrep named" 2>/dev/null | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('out-data','').strip())" || echo "none")
echo "   Current PID: ${OLD_PID}"

echo ""
echo "2. Killing bind (pebble will auto-restart)..."
ssh root@${PVE_HOST} "qm guest exec ${MAAS_VMID} -- pkill -9 named" 2>/dev/null || true

echo "   Waiting for restart..."
sleep 5

echo ""
echo "3. Verifying restart..."
NEW_PID=$(ssh root@${PVE_HOST} "qm guest exec ${MAAS_VMID} -- pgrep named" 2>/dev/null | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('out-data','').strip())" || echo "")

if [[ -n "$NEW_PID" && "$NEW_PID" != "$OLD_PID" ]]; then
    echo "   ✅ Bind restarted successfully (new PID: ${NEW_PID})"
else
    echo "   ❌ Bind may not have restarted properly"
    echo "   Check: ssh root@${PVE_HOST} 'qm guest exec ${MAAS_VMID} -- journalctl -u snap.maas.pebble -n 20'"
    exit 1
fi

echo ""
echo "4. Quick DNS test..."
TEST=$(ssh root@${PVE_HOST} "qm guest exec ${MAAS_VMID} -- bash -c 'host google.com 127.0.0.1'" 2>/dev/null | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('out-data',''))" | head -1)
echo "   $TEST"
