#!/bin/bash
# SAFE test script - only reads, never modifies anything

echo "=== SAFE Coral TPU Test (Read-Only) ==="
echo ""

# Check current Coral status
echo "1. Checking Coral TPU status..."
coral_device=$(lsusb | grep -E '18d1:9302|1a6e:089a')
if echo "$coral_device" | grep -q "18d1:9302"; then
    echo "   ✓ Coral is initialized (Google Inc mode)"
    echo "   Device: $coral_device"
    
    # Extract bus and device numbers
    bus=$(echo "$coral_device" | sed 's/Bus \([0-9]*\).*/\1/')
    device=$(echo "$coral_device" | sed 's/.*Device \([0-9]*\):.*/\1/')
    device_path="/dev/bus/usb/$(printf "%03d" $bus)/$(printf "%03d" $device)"
    echo "   Path: $device_path"
elif echo "$coral_device" | grep -q "1a6e:089a"; then
    echo "   ⚠ Coral needs initialization (Unichip mode)"
    echo "   Would need to run: python3 coral/pycoral/examples/classify_image.py ..."
else
    echo "   ✗ No Coral TPU detected"
fi

echo ""
echo "2. Checking current LXC configuration..."
current_dev0=$(grep "^dev0:" /etc/pve/lxc/113.conf 2>/dev/null | cut -d' ' -f2)
echo "   Current config: $current_dev0"

if [ -n "$device_path" ] && [ "$current_dev0" != "$device_path" ]; then
    echo "   ⚠ Config needs update: $current_dev0 -> $device_path"
else
    echo "   ✓ Config is correct"
fi

echo ""
echo "3. Checking container status..."
container_status=$(pct status 113 | grep -o 'status: [a-z]*' | cut -d' ' -f2)
echo "   Container 113 is: $container_status"

echo ""
echo "4. Checking Coral visibility inside container..."
if [ "$container_status" = "running" ]; then
    coral_in_lxc=$(pct exec 113 -- lsusb 2>/dev/null | grep -E '18d1:9302|1a6e:089a')
    if [ -n "$coral_in_lxc" ]; then
        echo "   ✓ Coral visible inside container:"
        echo "     $coral_in_lxc"
    else
        echo "   ✗ Coral NOT visible inside container"
    fi
else
    echo "   ⚠ Container not running, cannot check"
fi

echo ""
echo "5. What the automation WOULD do:"
echo "   - Check if Coral needs initialization"
echo "   - Run initialization if needed" 
echo "   - Get device path ($device_path)"
echo "   - Update config if needed"
echo "   - Restart container only if config changed"
echo ""
echo "NO CHANGES WERE MADE - This was a read-only test"