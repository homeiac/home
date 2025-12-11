#!/bin/bash
# Frigate Coral LXC - Start Container
# GitHub Issue: #168
# Starts the container (hookscript runs pre-start)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.env"

echo "=== Frigate Coral LXC - Start Container ==="
echo "Target host: $PVE_HOST_NAME ($PVE_HOST)"
echo ""

if [[ -z "$VMID" ]]; then
    echo "❌ ERROR: VMID not set in config.env"
    exit 1
fi

echo "Container VMID: $VMID"
echo ""

echo "1. Checking current container status..."
STATUS=$(ssh root@"$PVE_HOST" "pct status $VMID 2>/dev/null" || echo "NOT_FOUND")

if [[ "$STATUS" == "NOT_FOUND" ]]; then
    echo "   ❌ Container $VMID not found"
    exit 1
fi

echo "   Current status: $STATUS"

if echo "$STATUS" | grep -q "running"; then
    echo "   ✅ Container already running"
else
    echo ""
    echo "2. Starting container (hookscript will run first)..."
    ssh root@"$PVE_HOST" "pct start $VMID"
    echo "   ✅ Start command sent"

    echo ""
    echo "3. Waiting for container to start..."
    sleep 10

    echo ""
    echo "4. Verifying running status..."
    STATUS=$(ssh root@"$PVE_HOST" "pct status $VMID")
    echo "   $STATUS"

    if echo "$STATUS" | grep -q "running"; then
        echo "   ✅ Container started successfully"
    else
        echo "   ❌ Container may not have started"
        exit 1
    fi
fi

echo ""
echo "=== Container Start Complete ==="
echo ""
echo "NEXT: Run 31-verify-hookscript.sh to check hookscript execution"
