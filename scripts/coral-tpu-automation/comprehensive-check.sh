#!/bin/bash
# Comprehensive Coral TPU System Check
# This script performs a complete read-only analysis

echo "=================================================="
echo "   Comprehensive Coral TPU System Analysis"
echo "=================================================="
echo "Date: $(date)"
echo "Host: $(hostname)"
echo ""

# 1. Hardware Detection
echo "1. HARDWARE DETECTION"
echo "--------------------"
echo "All USB devices:"
lsusb
echo ""

echo "Coral-specific devices:"
coral_google=$(lsusb | grep '18d1:9302')
coral_unichip=$(lsusb | grep '1a6e:089a')

if [ -n "$coral_google" ]; then
    echo "✓ Coral in GOOGLE mode (initialized): $coral_google"
    coral_status="initialized"
    coral_device="$coral_google"
elif [ -n "$coral_unichip" ]; then
    echo "⚠ Coral in UNICHIP mode (needs init): $coral_unichip"
    coral_status="needs_init"
    coral_device="$coral_unichip"
else
    echo "✗ No Coral TPU detected"
    coral_status="missing"
    coral_device=""
fi
echo ""

# 2. Device Path Analysis
echo "2. DEVICE PATH ANALYSIS"
echo "-----------------------"
if [ "$coral_status" = "initialized" ]; then
    bus=$(echo "$coral_device" | sed 's/Bus \([0-9]*\).*/\1/')
    device=$(echo "$coral_device" | sed 's/.*Device \([0-9]*\):.*/\1/')
    detected_path="/dev/bus/usb/${bus}/${device}"
    
    echo "Bus number: $bus"
    echo "Device number: $device"
    echo "Calculated path: $detected_path"
    
    # Check if device file exists
    if [ -e "$detected_path" ]; then
        echo "✓ Device file exists: $(ls -l $detected_path)"
    else
        echo "✗ Device file missing: $detected_path"
    fi
else
    echo "N/A - Coral not in initialized state"
    detected_path=""
fi
echo ""

# 3. LXC Configuration Analysis
echo "3. LXC CONFIGURATION ANALYSIS"
echo "-----------------------------"
lxc_config="/etc/pve/lxc/113.conf"
echo "Config file: $lxc_config"

if [ -f "$lxc_config" ]; then
    echo "✓ Config file exists"
    
    # Extract current dev0 setting
    current_dev0=$(grep "^dev0:" "$lxc_config" | cut -d' ' -f2)
    echo "Current dev0 setting: $current_dev0"
    
    # Extract USB permission setting
    usb_permission=$(grep "lxc.cgroup2.devices.allow: c 189:\* rwm" "$lxc_config")
    if [ -n "$usb_permission" ]; then
        echo "✓ USB permissions configured: $usb_permission"
    else
        echo "⚠ USB permissions missing"
    fi
    
    # Show relevant config lines
    echo ""
    echo "Relevant config lines:"
    grep -E "^dev0:|lxc.cgroup2.devices.allow.*189|lxc.mount.entry.*usb" "$lxc_config" || echo "No USB-related entries found"
    
else
    echo "✗ Config file not found"
    current_dev0=""
fi
echo ""

# 4. Configuration Consistency Check
echo "4. CONFIGURATION CONSISTENCY CHECK"
echo "---------------------------------"
if [ "$coral_status" = "initialized" ] && [ -n "$current_dev0" ]; then
    if [ "$current_dev0" = "$detected_path" ]; then
        echo "✓ PERFECT: Config matches detected device"
        echo "  Detected: $detected_path"
        echo "  Config:   $current_dev0"
        config_status="correct"
    else
        echo "⚠ MISMATCH: Config does not match detected device"
        echo "  Detected: $detected_path"
        echo "  Config:   $current_dev0"
        config_status="needs_update"
    fi
elif [ "$coral_status" = "needs_init" ]; then
    echo "⚠ Coral needs initialization first"
    config_status="coral_needs_init"
else
    echo "✗ Cannot verify - missing data"
    config_status="unknown"
fi
echo ""

# 5. Container Status
echo "5. CONTAINER STATUS"
echo "------------------"
container_status=$(pct status 113 2>/dev/null | grep -o 'status: [a-z]*' | cut -d' ' -f2)
echo "Container 113 status: $container_status"

if [ "$container_status" = "running" ]; then
    echo "✓ Container is running"
    
    # Check if Coral is visible inside container
    echo ""
    echo "Coral visibility inside container:"
    coral_in_container=$(pct exec 113 -- lsusb 2>/dev/null | grep -E '18d1:9302|1a6e:089a')
    if [ -n "$coral_in_container" ]; then
        echo "✓ Coral visible: $coral_in_container"
        
        # Compare with host detection
        if [ "$coral_in_container" = "$coral_device" ]; then
            echo "✓ Container sees same device as host"
        else
            echo "⚠ Container sees different device than host"
            echo "  Host: $coral_device"
            echo "  Container: $coral_in_container"
        fi
    else
        echo "✗ Coral NOT visible inside container"
    fi
    
    # Check device permissions inside container
    echo ""
    echo "Device permissions inside container:"
    if [ -n "$detected_path" ]; then
        container_perms=$(pct exec 113 -- ls -l "$detected_path" 2>/dev/null)
        if [ -n "$container_perms" ]; then
            echo "✓ Device accessible: $container_perms"
        else
            echo "✗ Device not accessible in container"
        fi
    fi
else
    echo "⚠ Container not running - cannot check Coral visibility"
fi
echo ""

# 6. Frigate Configuration Check
echo "6. FRIGATE CONFIGURATION CHECK"
echo "------------------------------"
if [ "$container_status" = "running" ]; then
    frigate_config=$(pct exec 113 -- find /opt/frigate /etc/frigate /config -name "config.yml" 2>/dev/null | head -1)
    if [ -n "$frigate_config" ]; then
        echo "Frigate config found: $frigate_config"
        
        # Check for Coral configuration
        coral_config=$(pct exec 113 -- grep -A5 -B5 -i "coral\|edgetpu" "$frigate_config" 2>/dev/null)
        if [ -n "$coral_config" ]; then
            echo "✓ Coral configuration found in Frigate:"
            echo "$coral_config"
        else
            echo "⚠ No Coral configuration found in Frigate config"
        fi
    else
        echo "⚠ Frigate config file not found"
    fi
else
    echo "⚠ Cannot check - container not running"
fi
echo ""

# 7. System Health Summary
echo "7. SYSTEM HEALTH SUMMARY"
echo "------------------------"
case "$config_status" in
    "correct")
        echo "🟢 SYSTEM STATUS: OPTIMAL"
        echo "   - Coral TPU is initialized and working"
        echo "   - Configuration is correct"
        echo "   - No automation action needed"
        automation_needed="none"
        ;;
    "needs_update")
        echo "🟡 SYSTEM STATUS: NEEDS MINOR FIX"
        echo "   - Coral TPU is initialized"
        echo "   - Configuration needs updating"
        echo "   - Automation would fix this"
        automation_needed="config_update"
        ;;
    "coral_needs_init")
        echo "🟡 SYSTEM STATUS: NEEDS INITIALIZATION"
        echo "   - Coral TPU needs initialization"
        echo "   - Automation would run init script"
        automation_needed="coral_init"
        ;;
    *)
        echo "🔴 SYSTEM STATUS: NEEDS ATTENTION"
        echo "   - Manual investigation required"
        automation_needed="manual"
        ;;
esac
echo ""

# 8. Automation Recommendations
echo "8. AUTOMATION RECOMMENDATIONS"
echo "-----------------------------"
case "$automation_needed" in
    "none")
        echo "✓ No automation needed - system is working perfectly"
        echo "✓ The automation script should detect this and exit early"
        ;;
    "config_update")
        echo "→ Automation would:"
        echo "  1. Stop container 113"
        echo "  2. Update $lxc_config"
        echo "     Change: dev0: $current_dev0"
        echo "     To:     dev0: $detected_path"
        echo "  3. Start container 113"
        ;;
    "coral_init")
        echo "→ Automation would:"
        echo "  1. Run: python3 /root/code/coral/pycoral/examples/classify_image.py ..."
        echo "  2. Wait for device to switch to Google mode"
        echo "  3. Update LXC configuration"
        echo "  4. Restart container"
        ;;
    "manual")
        echo "⚠ Manual intervention required - automation should not run"
        ;;
esac
echo ""

# 9. Migration Status Check
echo "9. SAMSUNG T5 TO HDD MIGRATION STATUS"
echo "-------------------------------------"
migration_status=$(zfs list local-1TB-backup-new/subvol-113-disk-0 2>/dev/null)
if [ $? -eq 0 ]; then
    echo "✓ Migration in progress:"
    echo "$migration_status"
    
    original_size=$(zfs list -H -o used local-1TB-backup/subvol-113-disk-0 2>/dev/null)
    new_size=$(zfs list -H -o used local-1TB-backup-new/subvol-113-disk-0 2>/dev/null)
    echo "Original: $original_size"
    echo "Transferred: $new_size"
else
    echo "ℹ No active migration detected"
fi
echo ""

echo "=================================================="
echo "Analysis complete. All checks performed safely."
echo "No modifications were made to the system."
echo "=================================================="