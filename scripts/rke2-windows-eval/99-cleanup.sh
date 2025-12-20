#!/bin/bash
# Cleanup script to remove all RKE2 Windows eval VMs
set -e

PROXMOX_HOST="pumped-piglet.maas"
RANCHER_VMID=200
WINDOWS_VMID=201

echo "=== RKE2 Windows Eval Cleanup ==="
echo ""
echo "This will destroy the following VMs on ${PROXMOX_HOST}:"
echo "  - VM ${RANCHER_VMID} (rancher-server)"
echo "  - VM ${WINDOWS_VMID} (windows-worker)"
echo ""
read -p "Are you sure? (yes/no): " confirm

if [[ "$confirm" != "yes" ]]; then
    echo "Cancelled."
    exit 0
fi

echo ""
echo "Stopping and destroying VMs..."

# Stop and destroy Rancher VM
if ssh root@${PROXMOX_HOST} "qm status ${RANCHER_VMID}" 2>/dev/null; then
    echo "Stopping VM ${RANCHER_VMID}..."
    ssh root@${PROXMOX_HOST} "qm stop ${RANCHER_VMID} --skiplock 2>/dev/null || true"
    sleep 5
    echo "Destroying VM ${RANCHER_VMID}..."
    ssh root@${PROXMOX_HOST} "qm destroy ${RANCHER_VMID} --destroy-unreferenced-disks 1 --purge 1"
    echo "  VM ${RANCHER_VMID} destroyed"
else
    echo "  VM ${RANCHER_VMID} does not exist"
fi

# Stop and destroy Windows VM
if ssh root@${PROXMOX_HOST} "qm status ${WINDOWS_VMID}" 2>/dev/null; then
    echo "Stopping VM ${WINDOWS_VMID}..."
    ssh root@${PROXMOX_HOST} "qm stop ${WINDOWS_VMID} --skiplock 2>/dev/null || true"
    sleep 5
    echo "Destroying VM ${WINDOWS_VMID}..."
    ssh root@${PROXMOX_HOST} "qm destroy ${WINDOWS_VMID} --destroy-unreferenced-disks 1 --purge 1"
    echo "  VM ${WINDOWS_VMID} destroyed"
else
    echo "  VM ${WINDOWS_VMID} does not exist"
fi

echo ""
echo "Cleanup complete!"
echo ""
echo "Don't forget to remove DNS entry for rancher.homelab in OPNsense"
