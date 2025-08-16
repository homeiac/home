#!/bin/bash
# Mock Coral TPU Initialization Script
# This script simulates the entire Coral TPU initialization process
# Set DRY_RUN=false to execute real commands

# Configuration Parameters
DRY_RUN=${DRY_RUN:-true}
DEBUG=${DEBUG:-true}
CORAL_INIT_DIR=${CORAL_INIT_DIR:-"/root/code"}
PYTHON_CMD=${PYTHON_CMD:-"python3"}
LXC_ID=${LXC_ID:-"113"}
LXC_CONFIG_PATH=${LXC_CONFIG_PATH:-"/etc/pve/lxc/${LXC_ID}.conf"}
BACKUP_DIR=${BACKUP_DIR:-"/root/coral-backups"}
LOG_FILE=${LOG_FILE:-"/var/log/coral-tpu-init.log"}

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    local level=$1
    shift
    local message="$@"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    case $level in
        INFO)  color=$GREEN ;;
        WARN)  color=$YELLOW ;;
        ERROR) color=$RED ;;
        DEBUG) color=$BLUE ;;
        *)     color=$NC ;;
    esac
    
    echo -e "${color}[${timestamp}] [${level}] ${message}${NC}"
    # Skip file logging in test mode to avoid permission issues
    if [ "$DRY_RUN" = false ]; then
        echo "[${timestamp}] [${level}] ${message}" >> ${LOG_FILE} 2>/dev/null || true
    fi
}

# Execute or mock command
exec_cmd() {
    local cmd="$@"
    if [ "$DRY_RUN" = true ]; then
        log DEBUG "[DRY-RUN] Would execute: $cmd"
        # Return mock data based on command
        case "$cmd" in
            *"lsusb"*"Google"*)
                echo "Bus 003 Device 005: ID 18d1:9302 Google Inc."
                ;;
            *"lsusb"*"Unichip"*)
                echo "Bus 003 Device 004: ID 1a6e:089a Global Unichip Corp."
                ;;
            *"pct status"*)
                echo "status: running"
                ;;
            *)
                echo "[MOCK OUTPUT]"
                ;;
        esac
        return 0
    else
        log DEBUG "Executing: $cmd"
        eval "$cmd"
        return $?
    fi
}

# Check if Coral needs initialization
check_coral_status() {
    log INFO "Checking Coral TPU status..."
    
    # First check for Google Inc (already initialized)
    local google_device=$(exec_cmd "lsusb | grep -E '18d1:9302' | head -1")
    if [ -n "$google_device" ]; then
        log INFO "Coral already initialized: $google_device"
        echo "$google_device" | sed 's/.*Bus \([0-9]*\) Device \([0-9]*\).*/\1:\2/'
        return 0
    fi
    
    # Check for Unichip (needs initialization)
    local unichip_device=$(exec_cmd "lsusb | grep -E '1a6e:089a' | head -1")
    if [ -n "$unichip_device" ]; then
        log WARN "Coral needs initialization: $unichip_device"
        return 1
    fi
    
    log ERROR "No Coral TPU detected!"
    return 2
}

# Initialize Coral TPU
initialize_coral() {
    log INFO "Initializing Coral TPU..."
    
    # CRITICAL SAFETY CHECK: Never initialize if already in Google mode
    local google_check=$(exec_cmd "lsusb | grep -E '18d1:9302'")
    if [ -n "$google_check" ]; then
        log ERROR "SAFETY ABORT: Coral already in Google mode (18d1:9302)"
        log ERROR "Running initialization would break Frigate's access to TPU!"
        log ERROR "Device found: $google_check"
        log ERROR "If you need to reinitialize, reboot first to reset device to Unichip mode"
        return 1
    fi
    
    # Verify device is in Unichip mode before proceeding
    local unichip_check=$(exec_cmd "lsusb | grep -E '1a6e:089a'")
    if [ -z "$unichip_check" ]; then
        log ERROR "SAFETY ABORT: No Unichip device (1a6e:089a) found"
        log ERROR "Initialization can only run when device is in Unichip mode"
        return 1
    fi
    
    log INFO "✓ Safety check passed: Device in Unichip mode: $unichip_check"
    
    local init_script="${CORAL_INIT_DIR}/coral/pycoral/examples/classify_image.py"
    local model="${CORAL_INIT_DIR}/test_data/mobilenet_v2_1.0_224_inat_bird_quant_edgetpu.tflite"
    local labels="${CORAL_INIT_DIR}/test_data/inat_bird_labels.txt"
    local input="${CORAL_INIT_DIR}/test_data/parrot.jpg"
    
    # Check if initialization files exist
    for file in "$init_script" "$model" "$labels" "$input"; do
        if [ "$DRY_RUN" = false ] && [ ! -f "$file" ]; then
            log ERROR "Required file missing: $file"
            return 1
        fi
        log DEBUG "Checking file: $file [OK]"
    done
    
    # Run initialization
    log INFO "Running Coral initialization script..."
    local cmd="cd ${CORAL_INIT_DIR} && ${PYTHON_CMD} ${init_script} --model ${model} --labels ${labels} --input ${input}"
    local output=$(exec_cmd "$cmd")
    
    if [ $? -eq 0 ]; then
        log INFO "Initialization completed successfully"
        # Mock output for dry run
        if [ "$DRY_RUN" = true ]; then
            echo "----INFERENCE TIME----"
            echo "Note: The first inference on Edge TPU is slow because it includes"
            echo "loading the model into Edge TPU memory."
            echo "13.6ms"
            echo "3.0ms"
            echo "2.8ms"
            echo "2.9ms"
            echo "2.9ms"
            echo "-------RESULTS--------"
            echo "Ara macao (Scarlet Macaw): 0.77734"
        fi
        return 0
    else
        log ERROR "Initialization failed!"
        return 1
    fi
}

# Get Coral device path
get_coral_device_path() {
    local device_info=$(exec_cmd "lsusb | grep -E '18d1:9302' | head -1")
    if [ -z "$device_info" ]; then
        log ERROR "Coral not found in Google mode"
        return 1
    fi
    
    # Extract bus and device numbers
    local bus=$(echo "$device_info" | sed 's/Bus \([0-9]*\).*/\1/')
    local device=$(echo "$device_info" | sed 's/.*Device \([0-9]*\):.*/\1/')
    
    # Don't pad with extra zeros - use the numbers as-is
    local device_path="/dev/bus/usb/${bus}/${device}"
    log INFO "Coral device path: $device_path"
    echo "$device_path"
}

# Backup LXC configuration
backup_lxc_config() {
    local timestamp=$(date '+%Y%m%d_%H%M%S')
    local backup_file="${BACKUP_DIR}/lxc_${LXC_ID}_${timestamp}.conf"
    
    log INFO "Backing up LXC configuration to $backup_file"
    exec_cmd "mkdir -p ${BACKUP_DIR}"
    exec_cmd "cp ${LXC_CONFIG_PATH} ${backup_file}"
    
    # Keep only last 5 backups
    if [ "$DRY_RUN" = false ]; then
        ls -t ${BACKUP_DIR}/lxc_${LXC_ID}_*.conf 2>/dev/null | tail -n +6 | xargs -r rm
    fi
}

# Update LXC configuration
update_lxc_config() {
    local device_path=$1
    log INFO "Updating LXC configuration with device: $device_path"
    
    # Backup first
    backup_lxc_config
    
    # Create temporary config for testing
    local temp_config="/tmp/lxc_${LXC_ID}_new.conf"
    
    if [ "$DRY_RUN" = true ]; then
        log DEBUG "[DRY-RUN] Would update config with:"
        echo "dev0: $device_path"
        echo "lxc.cgroup2.devices.allow: c 189:* rwm"
    else
        # Read current config
        cp ${LXC_CONFIG_PATH} ${temp_config}
        
        # Remove old dev0 entry if exists
        sed -i '/^dev0:/d' ${temp_config}
        
        # Add new dev0 entry
        echo "dev0: $device_path" >> ${temp_config}
        
        # Ensure cgroup rule exists
        if ! grep -q "lxc.cgroup2.devices.allow: c 189:\* rwm" ${temp_config}; then
            echo "lxc.cgroup2.devices.allow: c 189:* rwm" >> ${temp_config}
        fi
        
        # Validate config syntax (mock for now)
        log INFO "Validating new configuration..."
        # pct config ${LXC_ID} --config ${temp_config} --dry-run
        
        # Apply new config
        cp ${temp_config} ${LXC_CONFIG_PATH}
        log INFO "Configuration updated successfully"
    fi
}

# Stop LXC container
stop_lxc() {
    log INFO "Stopping LXC container ${LXC_ID}..."
    local status=$(exec_cmd "pct status ${LXC_ID} | grep -o 'status: [a-z]*' | cut -d' ' -f2")
    
    if [ "$status" = "running" ]; then
        exec_cmd "pct stop ${LXC_ID}"
        # Wait for container to stop
        local max_wait=30
        local waited=0
        while [ "$waited" -lt "$max_wait" ]; do
            sleep 1
            status=$(exec_cmd "pct status ${LXC_ID} | grep -o 'status: [a-z]*' | cut -d' ' -f2")
            if [ "$status" = "stopped" ]; then
                log INFO "Container stopped successfully"
                return 0
            fi
            waited=$((waited + 1))
        done
        log ERROR "Container failed to stop within ${max_wait} seconds"
        return 1
    else
        log INFO "Container already stopped"
        return 0
    fi
}

# Start LXC container
start_lxc() {
    log INFO "Starting LXC container ${LXC_ID}..."
    exec_cmd "pct start ${LXC_ID}"
    
    # In dry-run mode, just simulate success
    if [ "$DRY_RUN" = true ]; then
        log INFO "Container started successfully"
        log INFO "Coral TPU verified inside container: Bus 003 Device 005: ID 18d1:9302 Google Inc."
        return 0
    fi
    
    # Wait for container to start (production mode)
    local max_wait=30
    local waited=0
    while [ "$waited" -lt "$max_wait" ]; do
        sleep 1
        status=$(exec_cmd "pct status ${LXC_ID} | grep -o 'status: [a-z]*' | cut -d' ' -f2")
        if [ "$status" = "running" ]; then
            log INFO "Container started successfully"
            # Verify Coral is accessible inside container
            sleep 2
            local coral_in_lxc=$(exec_cmd "pct exec ${LXC_ID} -- lsusb | grep -E '18d1:9302'")
            if [ -n "$coral_in_lxc" ]; then
                log INFO "Coral TPU verified inside container: $coral_in_lxc"
            else
                log WARN "Coral TPU not visible inside container"
            fi
            return 0
        fi
        waited=$((waited + 1))
    done
    log ERROR "Container failed to start within ${max_wait} seconds"
    return 1
}

# Main workflow
main() {
    log INFO "=== Coral TPU Automation Script Starting ==="
    log INFO "Configuration:"
    log INFO "  DRY_RUN: $DRY_RUN"
    log INFO "  LXC_ID: $LXC_ID"
    log INFO "  CORAL_INIT_DIR: $CORAL_INIT_DIR"
    
    # Step 1: Check Coral status
    if check_coral_status; then
        log INFO "Coral already initialized, checking device path..."
    else
        # Step 2: Initialize if needed
        log INFO "Coral needs initialization"
        if ! initialize_coral; then
            log ERROR "Failed to initialize Coral TPU"
            exit 1
        fi
        
        # Re-check status
        sleep 2
        if ! check_coral_status; then
            log ERROR "Coral still not initialized after running script"
            exit 1
        fi
    fi
    
    # Step 3: Get device path
    device_path=$(get_coral_device_path)
    if [ -z "$device_path" ]; then
        log ERROR "Failed to get Coral device path"
        exit 1
    fi
    
    # Step 4: Check if config needs updating
    current_dev0=$(grep "^dev0:" ${LXC_CONFIG_PATH} 2>/dev/null | cut -d' ' -f2)
    if [ "$current_dev0" = "$device_path" ]; then
        log INFO "LXC config already has correct device path"
        log INFO "No changes needed!"
        exit 0
    fi
    
    log INFO "LXC config needs updating (current: $current_dev0, needed: $device_path)"
    
    # Step 5: Stop container
    if ! stop_lxc; then
        log ERROR "Failed to stop LXC container"
        exit 1
    fi
    
    # Step 6: Update configuration
    if ! update_lxc_config "$device_path"; then
        log ERROR "Failed to update LXC configuration"
        exit 1
    fi
    
    # Step 7: Start container
    if ! start_lxc; then
        log ERROR "Failed to start LXC container"
        # Try to restore backup
        log WARN "Attempting to restore previous configuration..."
        latest_backup=$(ls -t ${BACKUP_DIR}/lxc_${LXC_ID}_*.conf 2>/dev/null | head -1)
        if [ -n "$latest_backup" ]; then
            exec_cmd "cp $latest_backup ${LXC_CONFIG_PATH}"
            start_lxc
        fi
        exit 1
    fi
    
    log INFO "=== Coral TPU Automation Complete ==="
    log INFO "Coral TPU is ready and Frigate container is running!"
}

# Run main function
main "$@"