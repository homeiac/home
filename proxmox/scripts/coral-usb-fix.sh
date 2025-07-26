#!/bin/bash
#
# Coral TPU USB Auto-mapping Script for Proxmox LXC
# 1. Check if Google device exists in lsusb
# 2. If missing, run Python script to initialize Coral TPU (convert generic to Google device)
# 3. Detect Google Coral TPU USB device and update LXC configuration if needed
#

set -euo pipefail

LOGFILE="/var/log/coral-usb-fix.log"
LXC_ID="113"
LXC_CONF="/etc/pve/lxc/${LXC_ID}.conf"
CORAL_CODE_DIR="/root/code"

log() {
    echo "$(date +%Y-%m-%d\ %H:%M:%S) - $1" >> "$LOGFILE"
    echo "$(date +%Y-%m-%d\ %H:%M:%S) - $1"
}

# Function to check if Google device exists
check_google_device_exists() {
    lsusb | grep -qi "google"
}

# Function to initialize Coral TPU by running Python script (when Google device is missing)
initialize_coral_tpu() {
    log "Google device not found - running Python script to initialize Coral TPU..."
    
    if [ ! -d "$CORAL_CODE_DIR" ]; then
        log "ERROR: Coral code directory $CORAL_CODE_DIR not found"
        return 1
    fi
    
    # Run the exact Python command as specified by user
    local test_result
    if test_result=$(cd "$CORAL_CODE_DIR" && python3 coral/pycoral/examples/classify_image.py --model test_data/mobilenet_v2_1.0_224_inat_bird_quant_edgetpu.tflite --labels test_data/inat_bird_labels.txt --input test_data/parrot.jpg 2>&1); then
        log "Coral TPU initialization SUCCESS - Google device should now be available"
        return 0
    else
        log "ERROR: Coral TPU initialization FAILED: $test_result"
        return 1
    fi
}

# Function to find Google Coral TPU USB device
find_coral_device() {
    local coral_device=""
    
    # Look for Google Coral Edge TPU USB device
    coral_device=$(lsusb | grep -i "google" | head -1 || true)
    
    if [ -z "$coral_device" ]; then
        log "ERROR: Google Coral TPU device not found after initialization"
        log "Available USB devices:"
        lsusb >> "$LOGFILE"
        return 1
    fi
    
    # Extract bus and device numbers
    local bus_num=$(echo "$coral_device" | sed "s/Bus \([0-9]*\) Device.*/\1/")
    local dev_num=$(echo "$coral_device" | sed "s/Bus [0-9]* Device \([0-9]*\).*/\1/")
    
    if [ -z "$bus_num" ] || [ -z "$dev_num" ]; then
        log "ERROR: Could not parse bus/device numbers from: $coral_device"
        return 1
    fi
    
    log "Found Google Coral TPU: Bus $bus_num Device $dev_num"
    echo "/dev/bus/usb/$bus_num/$dev_num"
}

# Function to update LXC configuration
update_lxc_config() {
    local device_path="$1"
    
    log "Updating LXC config for device: $device_path"
    
    # Backup current config
    cp "$LXC_CONF" "${LXC_CONF}.backup.$(date +%Y%m%d_%H%M%S)"
    
    # Remove existing dev0 line if present
    sed -i "/^dev0:/d" "$LXC_CONF"
    
    # Add new dev0 line with current USB mapping
    echo "dev0: $device_path" >> "$LXC_CONF"
    
    log "Updated $LXC_CONF with dev0: $device_path"
}

# Main execution
main() {
    log "=== Starting Coral TPU USB auto-mapping for Frigate LXC $LXC_ID ==="
    
    # Wait for USB devices to settle after boot
    sleep 15
    
    # Step 1: Check if Google device exists, initialize if missing
    if check_google_device_exists; then
        log "Google Coral TPU device already exists in lsusb - skipping initialization"
    else
        log "Google Coral TPU device not found - initialization required"
        if ! initialize_coral_tpu; then
            log "Failed to initialize Coral TPU, exiting"
            exit 1
        fi
    fi
    
    # Step 2: Find the Google Coral device
    local coral_device_path
    coral_device_path=$(find_coral_device)
    if [ $? -ne 0 ]; then
        log "Failed to find Google Coral TPU device"
        exit 1
    fi
    
    # Step 3: Check LXC config exists
    if [ ! -f "$LXC_CONF" ]; then
        log "ERROR: LXC config file $LXC_CONF not found"
        exit 1
    fi
    
    # Step 4: Check current mapping and update if needed
    local current_dev0=$(grep "^dev0:" "$LXC_CONF" | cut -d" " -f2 || true)
    if [ "$current_dev0" != "$coral_device_path" ]; then
        log "USB mapping needs update - Current: $current_dev0, Required: $coral_device_path"
        update_lxc_config "$coral_device_path"
        log "LXC configuration updated successfully"
    else
        log "USB mapping already correct: $coral_device_path"
    fi
    
    log "=== Coral TPU USB auto-mapping completed successfully ==="
}

# Run main function
main "$@"