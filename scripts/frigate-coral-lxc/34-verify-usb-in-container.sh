#!/bin/bash
# Frigate Coral LXC - Verify USB in Container
# GitHub Issue: #168
# Confirms USB device is visible inside the container

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.env"

echo "=== Frigate Coral LXC - Verify USB in Container ==="
echo "Target host: $PVE_HOST_NAME ($PVE_HOST)"
echo ""

if [[ -z "$VMID" ]]; then
    echo "❌ ERROR: VMID not set in config.env"
    exit 1
fi

echo "Container VMID: $VMID"
echo ""

echo "1. Checking container status..."
STATUS=$(ssh root@"$PVE_HOST" "pct status $VMID")
echo "   $STATUS"

if ! echo "$STATUS" | grep -q "running"; then
    echo "   ❌ Container is not running"
    exit 1
fi

echo ""
echo "2. Running lsusb inside container..."
LSUSB=$(ssh root@"$PVE_HOST" "pct exec $VMID -- lsusb 2>/dev/null" || echo "FAILED")

if [[ "$LSUSB" == "FAILED" ]]; then
    echo "   ❌ Could not run lsusb in container"
    echo "   lsusb may not be installed"
    exit 1
fi

echo "   All USB devices in container:"
echo "$LSUSB" | sed 's/^/   /'

echo ""
echo "3. Checking for Coral device..."
CORAL=$(echo "$LSUSB" | grep -E "($CORAL_VENDOR_UNINIT|$CORAL_VENDOR_INIT|Google)" || echo "NOT_FOUND")

if [[ "$CORAL" == "NOT_FOUND" ]]; then
    echo "   ❌ Coral USB device NOT visible in container"
    echo ""
    echo "   Troubleshooting:"
    echo "   - Check dev0 line in LXC config"
    echo "   - Check cgroup permissions"
    echo "   - Try restarting container"
    exit 1
fi

echo "   ✅ Coral USB device found in container:"
echo "   $CORAL"

echo ""
echo "4. Checking device file..."
DEV_PATH="/dev/bus/usb/$CORAL_BUS"
ssh root@"$PVE_HOST" "pct exec $VMID -- ls -la $DEV_PATH 2>/dev/null" || echo "   Could not list $DEV_PATH"

echo ""
echo "=== USB Verification Complete ==="
echo ""
echo "✅ All verifications passed! Coral USB is accessible in container."
