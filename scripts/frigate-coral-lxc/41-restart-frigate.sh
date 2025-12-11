#!/bin/bash
# Frigate Coral LXC - Restart Frigate Service
# GitHub Issue: #168
#
# Restarts Frigate to apply config changes

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.env"

echo "=== Frigate Coral LXC - Restart Frigate ==="
echo "Target host: $PVE_HOST_NAME ($PVE_HOST)"
echo "Container: $VMID"
echo ""

echo "1. Restarting Frigate service..."
ssh root@"$PVE_HOST" "pct exec $VMID -- systemctl restart frigate"
echo "   ✅ Restart command sent"

echo ""
echo "2. Waiting for Frigate to start (15 seconds)..."
sleep 15

echo ""
echo "3. Checking Frigate status..."
ssh root@"$PVE_HOST" "pct exec $VMID -- systemctl status frigate --no-pager" | head -10

echo ""
echo "=== Frigate Restart Complete ==="
echo ""
echo "NEXT: Run ./33-verify-coral-detection.sh to verify Coral TPU is working"
