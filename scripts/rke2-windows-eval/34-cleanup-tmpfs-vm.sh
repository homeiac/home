#!/bin/bash
# Clean up tmpfs VM and resources
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/.env" 2>/dev/null || true

PROXMOX_HOST="${PROXMOX_HOST:-pumped-piglet.maas}"

echo "=== Cleaning up tmpfs VM Resources ==="
echo ""

# Stop and destroy VM 203
echo "Destroying VM 203..."
ssh root@${PROXMOX_HOST} "qm stop 203 2>/dev/null || true; qm destroy 203 --purge 2>/dev/null || true"

# Clean up tmpfs disk
echo "Removing tmpfs disk..."
ssh root@${PROXMOX_HOST} "rm -f /mnt/ramdisk/vm-203-disk-0.qcow2"

# Optionally unmount tmpfs
echo ""
read -p "Unmount tmpfs? (y/N): " CONFIRM
if [[ "$CONFIRM" == "y" || "$CONFIRM" == "Y" ]]; then
    ssh root@${PROXMOX_HOST} "umount /mnt/ramdisk 2>/dev/null || true"
    echo "tmpfs unmounted."
fi

echo ""
echo "=== Cleanup Complete ==="
echo ""
echo "VM 201 (ZFS-backed) is still available."
echo "Golden image preserved at: /var/lib/vz/template/vm/windows-server-golden.raw.gz"
