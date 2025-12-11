#!/bin/bash
# Frigate Coral LXC - Find USB Sysfs Path
# GitHub Issue: #168
# Finds the sysfs path for hookscript USB reset

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.env"

echo "=== Frigate Coral LXC - Find Sysfs Path ==="
echo "Target host: $PVE_HOST_NAME ($PVE_HOST)"
echo ""

echo "1. Scanning /sys/bus/usb/devices/ for Coral..."
SYSFS_PATH=$(ssh root@"$PVE_HOST" 'for DEV in /sys/bus/usb/devices/*; do
    VENDOR=$(cat "$DEV/idVendor" 2>/dev/null)
    if [ "$VENDOR" = "1a6e" ] || [ "$VENDOR" = "18d1" ]; then
        echo "$(basename $DEV)"
        exit 0
    fi
done')

if [[ -z "$SYSFS_PATH" ]]; then
    echo "   ❌ Could not find Coral in sysfs"
    echo ""
    echo "   Available USB devices:"
    ssh root@"$PVE_HOST" "ls /sys/bus/usb/devices/ | grep -v ':'"
    exit 1
fi

echo "   ✅ Coral sysfs path: $SYSFS_PATH"

echo ""
echo "2. Getting device details..."
ssh root@"$PVE_HOST" "cat /sys/bus/usb/devices/$SYSFS_PATH/idVendor 2>/dev/null" | xargs echo "   Vendor ID:"
ssh root@"$PVE_HOST" "cat /sys/bus/usb/devices/$SYSFS_PATH/idProduct 2>/dev/null" | xargs echo "   Product ID:"
ssh root@"$PVE_HOST" "cat /sys/bus/usb/devices/$SYSFS_PATH/busnum 2>/dev/null" | xargs echo "   Bus Number:"
ssh root@"$PVE_HOST" "cat /sys/bus/usb/devices/$SYSFS_PATH/devnum 2>/dev/null" | xargs echo "   Device Number:"

echo ""
echo "=== Sysfs Path Discovery Complete ==="
echo ""
echo "Hookscript will use: $SYSFS_PATH"
echo "USB reset path: /sys/bus/usb/drivers/usb/$SYSFS_PATH"
