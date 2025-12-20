#!/bin/bash
# Setup tmpfs mount for RAM-backed VM disk
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/.env" 2>/dev/null || true

PROXMOX_HOST="${PROXMOX_HOST:-pumped-piglet.maas}"
# Golden image is 18GB, plus headroom for benchmark writes
TMPFS_SIZE="${TMPFS_SIZE:-25G}"
MOUNT_POINT="/mnt/ramdisk"

echo "=== Setting up tmpfs for VM Disk ==="
echo ""
echo "Host: ${PROXMOX_HOST}"
echo "Mount point: ${MOUNT_POINT}"
echo "Size: ${TMPFS_SIZE}"
echo ""

# Check available memory
echo "Checking available memory..."
ssh root@${PROXMOX_HOST} "free -h"
echo ""

AVAIL_GB=$(ssh root@${PROXMOX_HOST} "free -g | awk '/^Mem:/ {print \$7}'")
echo "Available RAM: ${AVAIL_GB}GB"

if [[ "$AVAIL_GB" -lt 25 ]]; then
    echo ""
    echo "WARNING: Less than 25GB available RAM"
    echo "You may need to shutdown some VMs first."
    echo ""
    echo "Current VMs:"
    ssh root@${PROXMOX_HOST} "qm list"
    echo ""
    read -p "Continue anyway? (y/N): " CONFIRM
    if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
        echo "Aborted. Free up RAM and try again."
        exit 1
    fi
fi

# Check if already mounted
if ssh root@${PROXMOX_HOST} "mountpoint -q ${MOUNT_POINT} 2>/dev/null"; then
    echo "tmpfs already mounted at ${MOUNT_POINT}"
    ssh root@${PROXMOX_HOST} "df -h ${MOUNT_POINT}"
    exit 0
fi

# Create mount point and mount tmpfs
echo "Creating mount point and mounting tmpfs..."
ssh root@${PROXMOX_HOST} "
    mkdir -p ${MOUNT_POINT}
    mount -t tmpfs -o size=${TMPFS_SIZE} tmpfs ${MOUNT_POINT}
    chmod 700 ${MOUNT_POINT}
"

# Verify
echo ""
echo "=== tmpfs Mounted ==="
ssh root@${PROXMOX_HOST} "df -h ${MOUNT_POINT}"
echo ""
echo "Next: Run ./32-create-tmpfs-vm.sh"
