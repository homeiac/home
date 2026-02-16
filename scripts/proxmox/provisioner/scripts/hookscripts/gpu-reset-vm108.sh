#!/bin/bash
# AMD RX 580 GPU Reset Hookscript for VM 108
# Handles the AMD GPU reset bug with automatic host reboot if GPU fails
#
# Problem: AMD Polaris GPUs (RX 570/580/590) have a known GPU Reset Bug where
# the GPU doesn't reset cleanly between VM uses.
#
# Solution: This hookscript:
# 1. Performs PCI reset on stop/start
# 2. After VM start, checks if GPU initialized properly (renderD128 exists)
# 3. If GPU stuck, automatically reboots host (with retry limits)
#
# Retry Logic:
# - Tracks reboot attempts in /var/run/gpu-reset-retries
# - Max 3 retries before giving up
# - Counter resets on successful GPU init
# - After max retries, VM starts but GPU may be broken (manual intervention needed)
#
# PCI Devices on still-fawn:
#   01:00.0 - AMD RX 580 GPU (1002:67df)
#   01:00.1 - AMD RX 580 HDMI Audio (1002:aaf0)

set -euo pipefail

VMID="$1"
PHASE="$2"

GPU_PCI="0000:01:00.0"
AUDIO_PCI="0000:01:00.1"
LOG_FILE="/var/log/gpu-reset.log"
RETRY_FILE="/var/run/gpu-reset-retries"
MAX_RETRIES=3
GPU_CHECK_DELAY=90  # seconds to wait for VM boot before checking GPU

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [VM $VMID] [$PHASE] $1" | tee -a "$LOG_FILE"
}

get_gpu_driver() {
    local driver
    driver=$(lspci -nnk -s 01:00.0 2>/dev/null | grep "Kernel driver in use:" | awk '{print $NF}') || true
    echo "${driver:-none}"
}

get_retry_count() {
    if [[ -f "$RETRY_FILE" ]]; then
        cat "$RETRY_FILE"
    else
        echo "0"
    fi
}

set_retry_count() {
    echo "$1" > "$RETRY_FILE"
}

reset_retry_count() {
    rm -f "$RETRY_FILE"
    log "Retry counter reset (GPU working)"
}

pci_reset_gpu() {
    log "Triggering PCI reset for GPU..."

    # Method 1: Use the device's reset file if available
    if [ -e "/sys/bus/pci/devices/$GPU_PCI/reset" ]; then
        log "Using /sys reset method"
        echo 1 > "/sys/bus/pci/devices/$GPU_PCI/reset" 2>/dev/null || true
        sleep 1
    fi

    # Method 2: Remove and rescan the device
    log "Removing and rescanning PCI device..."
    if [ -e "/sys/bus/pci/devices/$GPU_PCI/remove" ]; then
        echo 1 > "/sys/bus/pci/devices/$GPU_PCI/remove" 2>/dev/null || true
        sleep 1
    fi
    if [ -e "/sys/bus/pci/devices/$AUDIO_PCI/remove" ]; then
        echo 1 > "/sys/bus/pci/devices/$AUDIO_PCI/remove" 2>/dev/null || true
        sleep 1
    fi

    # Rescan PCI bus to re-detect the devices
    echo 1 > /sys/bus/pci/rescan 2>/dev/null || true
    sleep 2

    local driver
    driver=$(get_gpu_driver)
    log "GPU driver after reset: $driver"
}

ensure_vfio_bound() {
    log "Ensuring GPU is bound to vfio-pci..."

    local driver
    driver=$(get_gpu_driver)

    if [ "$driver" == "vfio-pci" ]; then
        log "GPU already bound to vfio-pci"
        return 0
    fi

    # If bound to something else, unbind first
    if [ "$driver" != "none" ] && [ -e "/sys/bus/pci/devices/$GPU_PCI/driver/unbind" ]; then
        log "Unbinding GPU from $driver..."
        echo "$GPU_PCI" > "/sys/bus/pci/devices/$GPU_PCI/driver/unbind" 2>/dev/null || true
        sleep 1
    fi

    # Bind to vfio-pci
    if [ ! -e "/sys/bus/pci/drivers/vfio-pci/$GPU_PCI" ]; then
        echo "1002 67df" > /sys/bus/pci/drivers/vfio-pci/new_id 2>/dev/null || true
        echo "$GPU_PCI" > /sys/bus/pci/drivers/vfio-pci/bind 2>/dev/null || true
    fi
    if [ ! -e "/sys/bus/pci/drivers/vfio-pci/$AUDIO_PCI" ]; then
        echo "1002 aaf0" > /sys/bus/pci/drivers/vfio-pci/new_id 2>/dev/null || true
        echo "$AUDIO_PCI" > /sys/bus/pci/drivers/vfio-pci/bind 2>/dev/null || true
    fi
    sleep 1

    driver=$(get_gpu_driver)
    log "GPU driver after vfio bind: $driver"
}

check_gpu_in_vm() {
    # Check if renderD128 exists in the VM (indicates GPU initialized properly)
    local result
    result=$(qm guest exec "$VMID" -- ls /dev/dri/renderD128 2>/dev/null) || true
    if echo "$result" | grep -q "renderD128"; then
        return 0  # GPU working
    else
        return 1  # GPU not working
    fi
}

wait_for_guest_agent() {
    local timeout=$1
    local elapsed=0
    log "Waiting for QEMU guest agent (max ${timeout}s)..."

    while [ $elapsed -lt $timeout ]; do
        if qm guest exec "$VMID" -- echo "ping" >/dev/null 2>&1; then
            log "Guest agent ready after ${elapsed}s"
            return 0
        fi
        sleep 5
        elapsed=$((elapsed + 5))
    done

    log "Guest agent not ready after ${timeout}s"
    return 1
}

ensure_guest_agent_running() {
    log "Ensuring qemu-guest-agent is running in VM..."

    # Try to start/restart the guest agent via qm guest exec
    # If agent isn't responding, we can't do much - but try anyway
    local result
    result=$(qm guest exec "$VMID" -- systemctl is-active qemu-guest-agent 2>/dev/null) || true

    if echo "$result" | grep -q "active"; then
        log "Guest agent already active"
        return 0
    fi

    log "Guest agent not active, attempting to start..."
    qm guest exec "$VMID" -- systemctl start qemu-guest-agent 2>/dev/null || true
    sleep 2

    # Verify it started
    result=$(qm guest exec "$VMID" -- systemctl is-active qemu-guest-agent 2>/dev/null) || true
    if echo "$result" | grep -q "active"; then
        log "Guest agent started successfully"
        return 0
    else
        log "WARNING: Could not start guest agent"
        return 1
    fi
}

handle_gpu_check() {
    local retries
    retries=$(get_retry_count)

    log "Checking GPU status in VM (retry count: $retries/$MAX_RETRIES)..."

    # Wait for VM to boot
    log "Waiting ${GPU_CHECK_DELAY}s for VM to boot..."
    sleep "$GPU_CHECK_DELAY"

    # Wait for guest agent
    if ! wait_for_guest_agent 120; then
        log "WARNING: Guest agent not responding, cannot check GPU"
        return 1
    fi

    # Ensure guest agent is running
    ensure_guest_agent_running || true

    # Check for renderD128
    local check_start=$SECONDS
    while [ $((SECONDS - check_start)) -lt 30 ]; do
        if check_gpu_in_vm; then
            log "SUCCESS: GPU initialized properly (/dev/dri/renderD128 exists)"
            reset_retry_count
            return 0
        fi
        sleep 5
    done

    # GPU failed to initialize
    log "FAILURE: GPU did not initialize (/dev/dri/renderD128 missing)"

    if [ "$retries" -ge "$MAX_RETRIES" ]; then
        log "ERROR: Max retries ($MAX_RETRIES) exceeded. Giving up on GPU recovery."
        log "Manual intervention required. Try: ssh root@still-fawn.maas reboot"
        reset_retry_count  # Reset for next time
        return 1
    fi

    # Increment retry counter and reboot
    retries=$((retries + 1))
    set_retry_count "$retries"
    log "Initiating host reboot (attempt $retries/$MAX_RETRIES)..."

    # Schedule reboot in background (allows hookscript to exit cleanly)
    nohup bash -c "sleep 5 && /sbin/reboot" >/dev/null 2>&1 &

    log "Host reboot scheduled in 5 seconds"
    return 0
}

case "$PHASE" in
    pre-start)
        log "=== PRE-START: Preparing GPU for passthrough ==="
        CURRENT_DRIVER=$(get_gpu_driver)
        log "Current GPU driver: $CURRENT_DRIVER"

        # Ensure GPU is bound to vfio-pci for passthrough
        ensure_vfio_bound
        log "GPU ready for passthrough"
        ;;

    post-start)
        log "=== POST-START: VM started, will check GPU status ==="

        # Run GPU check in background so hookscript returns quickly
        nohup /var/lib/vz/snippets/gpu-reset-vm108.sh "$VMID" gpu-check-background >> "$LOG_FILE" 2>&1 &

        log "GPU check scheduled in background (PID: $!)"
        ;;

    gpu-check-background)
        # Called from background process after post-start
        log "=== GPU-CHECK: Running background GPU verification ==="
        handle_gpu_check
        ;;

    post-stop)
        log "=== POST-STOP: Resetting GPU after VM stop ==="
        # Wait for VM to fully release the device
        sleep 3

        CURRENT_DRIVER=$(get_gpu_driver)
        log "Current GPU driver: $CURRENT_DRIVER"

        # Reset the GPU to clear any stuck state
        pci_reset_gpu

        # Re-bind to vfio-pci
        ensure_vfio_bound

        log "GPU reset complete, ready for next VM start"
        ;;

    pre-stop)
        log "=== PRE-STOP: VM stopping ==="
        # No action needed - just log
        ;;

    *)
        log "Unknown phase: $PHASE"
        ;;
esac

exit 0

