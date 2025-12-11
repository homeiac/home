#!/bin/bash
# Frigate Coral LXC - Stop Container
# GitHub Issue: #168
# Stops the container for configuration changes

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.env"

echo "=== Frigate Coral LXC - Stop Container ==="
echo "Target host: $PVE_HOST_NAME ($PVE_HOST)"
echo ""

if [[ -z "$VMID" ]]; then
    echo "❌ ERROR: VMID not set in config.env"
    echo "   Please update VMID after creating the container"
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

if echo "$STATUS" | grep -q "stopped"; then
    echo "   ✅ Container already stopped"
else
    echo ""
    echo "2. Stopping container..."
    ssh root@"$PVE_HOST" "pct stop $VMID"
    echo "   ✅ Stop command sent"

    echo ""
    echo "3. Waiting for container to stop..."
    sleep 5

    echo ""
    echo "4. Verifying stopped status..."
    STATUS=$(ssh root@"$PVE_HOST" "pct status $VMID")
    echo "   $STATUS"

    if echo "$STATUS" | grep -q "stopped"; then
        echo "   ✅ Container stopped successfully"
    else
        echo "   ❌ Container may not have stopped cleanly"
        exit 1
    fi
fi

echo ""
echo "=== Container Stop Complete ==="
