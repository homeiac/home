#!/bin/bash
# Create VM 203 with tmpfs-backed disk from golden image
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/.env" 2>/dev/null || true

PROXMOX_HOST="${PROXMOX_HOST:-pumped-piglet.maas}"
VMID=203
VM_NAME="windows-tmpfs-test"
GOLDEN_QCOW2="/var/lib/vz/template/vm/windows-server-golden.qcow2"
TMPFS_DISK="/mnt/ramdisk/vm-${VMID}-disk-0.qcow2"

echo "=== Creating tmpfs-backed Windows VM ==="
echo ""
echo "VMID: ${VMID}"
echo "Name: ${VM_NAME}"
echo "Source: ${GOLDEN_IMAGE_GZ}"
echo "Disk: ${TMPFS_DISK}"
echo ""

# Check prerequisites
echo "Checking prerequisites..."

# Golden image exists?
if ! ssh root@${PROXMOX_HOST} "test -f ${GOLDEN_QCOW2}"; then
    echo "ERROR: Golden image not found at ${GOLDEN_QCOW2}"
    echo "Run ./30-create-golden-image.sh first"
    exit 1
fi

# tmpfs mounted?
if ! ssh root@${PROXMOX_HOST} "mountpoint -q /mnt/ramdisk"; then
    echo "ERROR: tmpfs not mounted at /mnt/ramdisk"
    echo "Run ./31-setup-tmpfs.sh first"
    exit 1
fi

# VM already exists?
if ssh root@${PROXMOX_HOST} "qm status ${VMID}" 2>/dev/null; then
    echo "VM ${VMID} already exists. Destroying..."
    ssh root@${PROXMOX_HOST} "qm stop ${VMID} 2>/dev/null || true; qm destroy ${VMID} --purge"
fi

# Copy golden image to tmpfs (qcow2 is already sparse/compressed)
echo ""
echo "Copying golden image to tmpfs..."
echo "This takes 1-2 minutes..."
ssh root@${PROXMOX_HOST} "cp ${GOLDEN_QCOW2} ${TMPFS_DISK}"

echo "Disk created:"
ssh root@${PROXMOX_HOST} "ls -lh ${TMPFS_DISK}"

# Register tmpfs as a directory storage (temporary)
echo "Registering tmpfs as storage..."
ssh root@${PROXMOX_HOST} "
    # Add tmpfs as a directory storage if not exists
    if ! grep -q 'dir: tmpfs-ramdisk' /etc/pve/storage.cfg; then
        cat >> /etc/pve/storage.cfg << 'STORAGECFG'

dir: tmpfs-ramdisk
    path /mnt/ramdisk
    content images
    nodes pumped-piglet
STORAGECFG
    fi
"

# Create VM with tmpfs disk
echo ""
echo "Creating VM ${VMID}..."

# First rename disk to match Proxmox naming convention
ssh root@${PROXMOX_HOST} "mv ${TMPFS_DISK} /mnt/ramdisk/${VMID}/disk-0.qcow2 2>/dev/null || mkdir -p /mnt/ramdisk/${VMID} && mv ${TMPFS_DISK} /mnt/ramdisk/${VMID}/disk-0.qcow2"

ssh root@${PROXMOX_HOST} "
    # Create VM (copy settings from VM 201)
    qm create ${VMID} --name ${VM_NAME} \
        --cores 8 \
        --memory 16384 \
        --net0 virtio,bridge=vmbr0 \
        --ostype win11 \
        --cpu host \
        --scsihw virtio-scsi-pci \
        --agent 1

    # Attach tmpfs disk through the registered storage
    qm set ${VMID} --scsi0 tmpfs-ramdisk:${VMID}/disk-0.qcow2,cache=writeback

    # Set boot order
    qm set ${VMID} --boot order=scsi0
"

echo ""
echo "=== VM ${VMID} Created ==="
ssh root@${PROXMOX_HOST} "qm config ${VMID}"

echo ""
echo "Starting VM..."
ssh root@${PROXMOX_HOST} "qm start ${VMID}"

echo ""
echo "=== VM Started ==="
echo ""
echo "NOTE: This VM uses the same Windows install as VM 201"
echo "It will have the same IP (192.168.4.201) configured - may cause conflicts!"
echo ""
echo "For benchmarking, shutdown VM 201 first, or change IP in Windows."
echo ""
echo "Next: Run ./33-benchmark-tmpfs.sh"
