#!/bin/bash
# Frigate Coral LXC - Reload Udev Rules and Initialize Coral
# GitHub Issue: #168
# Reference: docs/source/md/coral-tpu-automation-runbook.md
#
# Reloads udev rules and triggers Coral firmware loading
# After this, Coral should switch from 1a6e:089a to 18d1:9302

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.env"

echo "=== Frigate Coral LXC - Reload Udev Rules ==="
echo "Target host: $PVE_HOST_NAME ($PVE_HOST)"
echo ""

echo "1. Checking Coral state BEFORE reload..."
BEFORE_STATE=$(ssh root@"$PVE_HOST" "lsusb | grep -E '1a6e:089a|18d1:9302'" 2>/dev/null || echo "NOT FOUND")
echo "   $BEFORE_STATE"

echo ""
echo "2. Reloading udev rules..."
ssh root@"$PVE_HOST" "udevadm control --reload-rules"
echo "   ✅ Rules reloaded"

echo ""
echo "3. Triggering udev re-detection (this loads firmware if Coral in bootloader mode)..."
ssh root@"$PVE_HOST" "udevadm trigger --subsystem-match=usb --action=add"
echo "   ✅ Trigger complete"

echo ""
echo "4. Waiting for firmware load and device re-enumeration..."
sleep 3

echo ""
echo "5. Checking Coral state AFTER reload..."
AFTER_STATE=$(ssh root@"$PVE_HOST" "lsusb | grep -E '1a6e:089a|18d1:9302'" 2>/dev/null || echo "NOT FOUND")
echo "   $AFTER_STATE"

if echo "$AFTER_STATE" | grep -q "18d1:9302"; then
    echo ""
    echo "   ✅ Coral initialized successfully (18d1:9302 Google Inc)"
elif echo "$AFTER_STATE" | grep -q "1a6e:089a"; then
    echo ""
    echo "   ⚠️  Coral still in bootloader mode (1a6e:089a)"
    echo "   Trying manual dfu-util initialization..."
    ssh root@"$PVE_HOST" "dfu-util -D /usr/local/lib/firmware/apex_latest_single_ep.bin -d '1a6e:089a' -R" || true
    sleep 2
    RETRY_STATE=$(ssh root@"$PVE_HOST" "lsusb | grep -E '1a6e:089a|18d1:9302'" 2>/dev/null || echo "NOT FOUND")
    echo "   After manual init: $RETRY_STATE"
    if echo "$RETRY_STATE" | grep -q "18d1:9302"; then
        echo "   ✅ Manual initialization succeeded"
    else
        echo "   ❌ Manual initialization failed - may need USB replug"
    fi
else
    echo ""
    echo "   ❌ Coral USB not detected at all!"
fi

echo ""
echo "6. Getting current USB bus/device for config..."
CORAL_INFO=$(ssh root@"$PVE_HOST" "lsusb | grep '18d1:9302'" 2>/dev/null || echo "")
if [ -n "$CORAL_INFO" ]; then
    NEW_BUS=$(echo "$CORAL_INFO" | sed 's/Bus \([0-9]*\) Device.*/\1/')
    NEW_DEV=$(echo "$CORAL_INFO" | sed 's/.*Device \([0-9]*\):.*/\1/')
    echo "   Coral USB path: /dev/bus/usb/$NEW_BUS/$NEW_DEV"
fi

echo ""
echo "=== Udev Reload Complete ==="
echo ""
echo "NEXT: Run Phase 3 (Container Creation) or Phase 4 (USB Passthrough)"
