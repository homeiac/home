#!/bin/bash
# Destroy only the Linux VMs (preserve Windows VM 201)
set -e

PROXMOX_HOST="${PROXMOX_HOST:-pumped-piglet.maas}"

echo "=== Destroying Linux VMs (preserving Windows) ==="
echo ""
echo "Will delete:"
echo "  - VM 200 (rancher-mgmt)"
echo "  - VM 202 (linux-control)"
echo ""
echo "Will KEEP:"
echo "  - VM 201 (windows-worker)"
echo ""

for VMID in 200 202; do
    echo "Destroying VM $VMID..."
    ssh root@${PROXMOX_HOST} "qm stop $VMID 2>/dev/null || true; qm destroy $VMID --purge 2>/dev/null || true"
done

echo ""
echo "=== Done ==="
echo "Windows VM 201 preserved."
echo "Run ./01-create-rancher-vm.sh to start fresh."
