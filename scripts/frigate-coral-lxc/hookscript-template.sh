#!/bin/bash
# Coral LXC Hookscript Template
# GitHub Issue: #168
# This is deployed to /var/lib/vz/snippets/coral-lxc-hook-<VMID>.sh on the host
#
# Features:
# - Detects Coral by vendor ID (1a6e uninitialized, 18d1 initialized)
# - Performs USB unbind/bind reset before container start
# - Updates dev0 path in LXC config after reset (device number may change)
# - Logs all actions to syslog

VMID=$1
PHASE=$2

# Only run on pre-start for specific VMID
if [ "$PHASE" != "pre-start" ]; then
    exit 0
fi

LOG_TAG="coral-hook-$VMID"
log() { logger -t "$LOG_TAG" "$1"; echo "$1"; }

log "=== Coral USB Reset Hookscript for LXC $VMID ==="
log "Phase: $PHASE"

# Find Coral USB device by vendor ID
USB_PATH=""
for DEV in /sys/bus/usb/devices/*; do
    VENDOR=$(cat "$DEV/idVendor" 2>/dev/null)
    if [ "$VENDOR" = "1a6e" ] || [ "$VENDOR" = "18d1" ]; then
        USB_PATH=$(basename "$DEV")
        log "Found Coral at sysfs: $USB_PATH (vendor: $VENDOR)"
        break
    fi
done

if [ -z "$USB_PATH" ]; then
    log "WARNING: Coral USB device not found - skipping reset"
    exit 0
fi

# Perform USB reset (unbind/rebind)
if [ -e "/sys/bus/usb/drivers/usb/$USB_PATH" ]; then
    log "Resetting USB device $USB_PATH..."

    # Unbind
    echo "$USB_PATH" > /sys/bus/usb/drivers/usb/unbind 2>/dev/null || true
    log "Unbind complete, waiting 2 seconds..."
    sleep 2

    # Rebind
    echo "$USB_PATH" > /sys/bus/usb/drivers/usb/bind 2>/dev/null || true
    log "Rebind complete, waiting 3 seconds for device to settle..."
    sleep 3
else
    log "Device $USB_PATH not bound to usb driver - skipping reset"
fi

# Update dev0 path in LXC config (device number may have changed after reset)
CORAL_BUS=$(cat "/sys/bus/usb/devices/$USB_PATH/busnum" 2>/dev/null)
CORAL_DEV=$(cat "/sys/bus/usb/devices/$USB_PATH/devnum" 2>/dev/null)

if [ -n "$CORAL_BUS" ] && [ -n "$CORAL_DEV" ]; then
    NEW_PATH=$(printf "/dev/bus/usb/%03d/%03d" "$CORAL_BUS" "$CORAL_DEV")
    log "Updating dev0 to: $NEW_PATH"
    sed -i "s|^dev0:.*|dev0: ${NEW_PATH},mode=0666|" "/etc/pve/lxc/$VMID.conf"
    log "LXC config updated"
else
    log "WARNING: Could not read bus/dev numbers for $USB_PATH"
fi

log "=== Hookscript complete ==="
exit 0
