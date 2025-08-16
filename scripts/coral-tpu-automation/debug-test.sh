#!/bin/bash
# Debug the coral detection logic

echo "=== Debug Coral Detection ==="

# Real detection
real_device=$(lsusb | grep '18d1:9302')
echo "Real lsusb output: $real_device"

if [ -n "$real_device" ]; then
    bus=$(echo "$real_device" | sed 's/Bus \([0-9]*\).*/\1/')
    device=$(echo "$real_device" | sed 's/.*Device \([0-9]*\):.*/\1/')
    device_path="/dev/bus/usb/${bus}/${device}"
    echo "Detected path: $device_path"
else
    echo "No Coral detected"
    exit 1
fi

# Current config
current_dev0=$(grep "^dev0:" /etc/pve/lxc/113.conf | cut -d' ' -f2)
echo "Current config: $current_dev0"

# Compare
if [ "$current_dev0" = "$device_path" ]; then
    echo "✓ Config is CORRECT - no changes needed"
else
    echo "✗ Config WRONG - would need update"
    echo "  From: $current_dev0"
    echo "  To:   $device_path"
fi