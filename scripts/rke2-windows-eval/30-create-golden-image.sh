#!/bin/bash
# Create a golden Windows disk image from VM 201
# This creates a compressed copy without affecting the running VM
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/.env" 2>/dev/null || true

PROXMOX_HOST="${PROXMOX_HOST:-pumped-piglet.maas}"
SOURCE_VMID=201
GOLDEN_IMAGE="/var/lib/vz/template/vm/windows-server-golden.raw"
GOLDEN_IMAGE_GZ="${GOLDEN_IMAGE}.gz"

echo "=== Creating Golden Windows Image ==="
echo ""
echo "Source: VM ${SOURCE_VMID}"
echo "Destination: ${GOLDEN_IMAGE_GZ}"
echo ""

# Find the boot disk from VM config
echo "Finding boot disk..."
DISK_CONFIG=$(ssh root@${PROXMOX_HOST} "qm config ${SOURCE_VMID} | grep '^scsi0:'")
echo "Disk config: ${DISK_CONFIG}"

# Extract the volume name (e.g., local-2TB-zfs:vm-201-disk-2)
VOLUME=$(echo "$DISK_CONFIG" | sed 's/scsi0: //' | cut -d',' -f1)
echo "Volume: ${VOLUME}"

# Extract disk name (e.g., vm-201-disk-2)
DISK_NAME=$(echo "$VOLUME" | cut -d':' -f2)
echo "Disk name: ${DISK_NAME}"

# Get the storage name
STORAGE=$(echo "$VOLUME" | cut -d':' -f1)
echo "Storage: ${STORAGE}"

# Create template directory if needed
ssh root@${PROXMOX_HOST} "mkdir -p /var/lib/vz/template/vm"

GOLDEN_QCOW2="/var/lib/vz/template/vm/windows-server-golden.qcow2"

# Check if golden image already exists
if ssh root@${PROXMOX_HOST} "test -f ${GOLDEN_QCOW2}"; then
    echo ""
    echo "Golden image already exists at ${GOLDEN_QCOW2}"
    echo "Size: $(ssh root@${PROXMOX_HOST} "ls -lh ${GOLDEN_QCOW2} | awk '{print \$5}'")"
    read -p "Overwrite? (y/N): " CONFIRM
    if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
        echo "Aborted."
        exit 0
    fi
fi

# Get the ZFS volume name and device path
ZFS_VOL="${STORAGE}/${DISK_NAME}"
ZVOL_DEV="/dev/zvol/${ZFS_VOL}"
echo "ZFS volume: ${ZFS_VOL}"
echo "Device: ${ZVOL_DEV}"

# Verify VM is stopped (required for consistent copy without snapshot)
VM_STATUS=$(ssh root@${PROXMOX_HOST} "qm status ${SOURCE_VMID} | awk '{print \$2}'")
if [[ "$VM_STATUS" == "running" ]]; then
    echo ""
    echo "ERROR: VM ${SOURCE_VMID} is running. Stop it first for consistent copy."
    echo "Run: ./35-shutdown-cluster.sh"
    exit 1
fi
echo "VM ${SOURCE_VMID} is stopped - safe to copy"

# Export as SPARSE qcow2 (only stores actual data, not zeros)
echo ""
echo "Converting to sparse qcow2 format..."
echo "This will only store actual data (~22GB), not the full 200GB"
echo "This may take 5-10 minutes..."
echo ""
ssh root@${PROXMOX_HOST} "qemu-img convert -p -f raw -O qcow2 ${ZVOL_DEV} ${GOLDEN_QCOW2}"

# Show result
echo ""
echo "=== Golden Image Created ==="
ssh root@${PROXMOX_HOST} "ls -lh ${GOLDEN_QCOW2}"
ssh root@${PROXMOX_HOST} "qemu-img info ${GOLDEN_QCOW2}"
echo ""
echo "Next: Run ./31-setup-tmpfs.sh"
