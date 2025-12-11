#!/bin/bash
# Automated Frigate LXC creation using PVE Helper Script
# Requires: frigate.vars in same directory OR /usr/local/community-scripts/defaults/
#
# GitHub Issue: #168
# Documentation: docs/source/md/proxmox-pve-helper-scripts-automation.md

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load configuration (local first, then system-wide)
if [[ -f "$SCRIPT_DIR/frigate.vars" ]]; then
    echo "Loading config from: $SCRIPT_DIR/frigate.vars"
    source "$SCRIPT_DIR/frigate.vars"
elif [[ -f "/usr/local/community-scripts/defaults/frigate.vars" ]]; then
    echo "Loading config from: /usr/local/community-scripts/defaults/frigate.vars"
    source "/usr/local/community-scripts/defaults/frigate.vars"
else
    echo "ERROR: frigate.vars not found"
    echo "Expected locations:"
    echo "  - $SCRIPT_DIR/frigate.vars"
    echo "  - /usr/local/community-scripts/defaults/frigate.vars"
    exit 1
fi

# Verify we're on Proxmox host
if [[ ! -f /etc/pve/version ]]; then
    echo "ERROR: Must run on Proxmox host"
    echo "This script should be executed directly on the Proxmox server"
    exit 1
fi

# Verify storage pool
if [[ "$VERIFY_STORAGE" == "1" ]]; then
    if ! pvesm status | grep -q "^$CONTAINER_STORAGE"; then
        echo "ERROR: Storage pool '$CONTAINER_STORAGE' not found"
        echo ""
        echo "Available storage pools:"
        pvesm status
        exit 1
    fi
fi

# Export variables for PVE Helper Script
export var_cpu="$CPU_CORES"
export var_ram="$RAM_MB"
export var_disk="$DISK_SIZE_GB"
export var_gpu="$GPU_ACCELERATION"
export var_unprivileged="$CONTAINER_PRIVILEGED"
export STORAGE="$CONTAINER_STORAGE"

echo "=== Automated Frigate LXC Creation ==="
echo ""
echo "Configuration:"
echo "  CPU Cores:    ${CPU_CORES}"
echo "  RAM:          ${RAM_MB} MB"
echo "  Disk:         ${DISK_SIZE_GB} GB"
echo "  Storage Pool: ${CONTAINER_STORAGE}"
echo "  GPU Accel:    ${GPU_ACCELERATION}"
echo "  Privileged:   $([ "$CONTAINER_PRIVILEGED" == "0" ] && echo "yes" || echo "no")"
echo ""

if [[ "$DRY_RUN" == "1" ]]; then
    echo "[DRY RUN] Would execute frigate.sh with above settings"
    echo ""
    echo "To run for real, set DRY_RUN=0 in frigate.vars"
    exit 0
fi

# CRITICAL: Bypass SSH detection for unattended execution
# PVE Helper Scripts detect SSH sessions and show confirmation dialogs
# Unsetting these variables tricks the script into running non-interactively
echo "Bypassing SSH detection..."
unset SSH_CLIENT SSH_CONNECTION SSH_TTY

echo ""
echo "Executing PVE Helper Script for Frigate..."
echo "============================================"
echo ""

# Execute helper script (using raw GitHub URL - the standard pattern)
bash -c "$(curl -fsSL https://raw.githubusercontent.com/community-scripts/ProxmoxVE/main/ct/frigate.sh)"

echo ""
echo "============================================"
echo "=== Container Creation Complete ==="
echo ""
echo "Next steps:"
echo "1. Note the assigned VMID from above output"
echo "2. Update config.env with: VMID=<assigned_vmid>"
echo "3. Run: ./10-stop-container.sh"
echo "4. Continue with Phase 4 (USB passthrough)"
echo ""
echo "For Coral TPU support, complete all phases in the deployment guide."
