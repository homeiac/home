#!/bin/bash
# Frigate Coral LXC - Download Coral Firmware
# GitHub Issue: #168
# Reference: docs/source/md/coral-tpu-automation-runbook.md

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.env"

FIRMWARE_DIR="/usr/local/lib/firmware"
FIRMWARE_FILE="apex_latest_single_ep.bin"
FIRMWARE_URL="https://github.com/google-coral/libedgetpu/raw/master/driver/usb/${FIRMWARE_FILE}"

echo "=== Frigate Coral LXC - Download Coral Firmware ==="
echo "Target host: $PVE_HOST_NAME ($PVE_HOST)"
echo ""

echo "1. Creating firmware directory..."
ssh root@"$PVE_HOST" "mkdir -p $FIRMWARE_DIR"
echo "   ✅ Created $FIRMWARE_DIR"

echo ""
echo "2. Checking if firmware already exists..."
if ssh root@"$PVE_HOST" "test -f $FIRMWARE_DIR/$FIRMWARE_FILE && echo exists" 2>/dev/null | grep -q exists; then
    echo "   ✅ Firmware already exists"
    ssh root@"$PVE_HOST" "ls -la $FIRMWARE_DIR/$FIRMWARE_FILE"
else
    echo "   Downloading firmware from Google libedgetpu repo..."
    ssh root@"$PVE_HOST" "wget -O $FIRMWARE_DIR/$FIRMWARE_FILE '$FIRMWARE_URL'"
    echo "   ✅ Firmware downloaded"
fi

echo ""
echo "3. Verifying firmware..."
ssh root@"$PVE_HOST" "ls -la $FIRMWARE_DIR/$FIRMWARE_FILE"
FIRMWARE_SIZE=$(ssh root@"$PVE_HOST" "stat -c%s $FIRMWARE_DIR/$FIRMWARE_FILE")
if [ "$FIRMWARE_SIZE" -gt 5000 ]; then
    echo "   ✅ Firmware size OK ($FIRMWARE_SIZE bytes)"
else
    echo "   ❌ Firmware too small ($FIRMWARE_SIZE bytes) - download may have failed"
    exit 1
fi

echo ""
echo "=== Firmware Download Complete ==="
echo ""
echo "NEXT: Run 05c-create-udev-rules.sh"
