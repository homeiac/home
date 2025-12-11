#!/bin/bash
# Frigate Coral LXC - Verify Coral USB Detection
# GitHub Issue: #168
# Confirms Coral USB device is visible via lsusb

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.env"

echo "=== Frigate Coral LXC - Verify Coral USB ==="
echo "Target host: $PVE_HOST_NAME ($PVE_HOST)"
echo ""

echo "1. Scanning for Coral USB devices..."
CORAL_LINE=$(ssh root@"$PVE_HOST" "lsusb | grep -E '($CORAL_VENDOR_UNINIT|$CORAL_VENDOR_INIT)'" || true)

if [[ -z "$CORAL_LINE" ]]; then
    echo "   ❌ No Coral USB device found!"
    echo "   Expected vendor IDs: $CORAL_VENDOR_UNINIT (uninitialized) or $CORAL_VENDOR_INIT (initialized)"
    echo ""
    echo "   Full lsusb output:"
    ssh root@"$PVE_HOST" "lsusb"
    exit 1
fi

echo "   ✅ Coral device found:"
echo "   $CORAL_LINE"

# Parse bus and device
BUS=$(echo "$CORAL_LINE" | sed 's/Bus \([0-9]*\) Device.*/\1/')
DEV=$(echo "$CORAL_LINE" | sed 's/Bus [0-9]* Device \([0-9]*\).*/\1/')
VENDOR=$(echo "$CORAL_LINE" | grep -oE "($CORAL_VENDOR_UNINIT|$CORAL_VENDOR_INIT)")

echo ""
echo "   Bus: $BUS"
echo "   Device: $DEV"
echo "   Vendor ID: $VENDOR"

if [[ "$VENDOR" == "$CORAL_VENDOR_UNINIT" ]]; then
    echo "   Status: Uninitialized (will initialize on first use)"
elif [[ "$VENDOR" == "$CORAL_VENDOR_INIT" ]]; then
    echo "   Status: Initialized (Google mode)"
fi

echo ""
echo "2. Checking device path accessibility..."
DEV_PATH="/dev/bus/usb/$BUS/$DEV"
if ssh root@"$PVE_HOST" "ls -la $DEV_PATH" 2>/dev/null; then
    echo "   ✅ Device path accessible: $DEV_PATH"
else
    echo "   ❌ Device path not accessible: $DEV_PATH"
    exit 1
fi

echo ""
echo "=== Coral USB Verification Complete ==="
echo ""
echo "Update config.env if needed:"
echo "  CORAL_BUS=\"$BUS\""
echo "  CORAL_DEV=\"$DEV\""
