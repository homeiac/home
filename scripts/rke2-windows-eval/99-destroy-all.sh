#!/bin/bash
# Destroy all RKE2 Windows eval resources
# This is the nuclear reset - deletes VMs, cluster, everything
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/.env" 2>/dev/null || true

PROXMOX_HOST="${PROXMOX_HOST:-pumped-piglet.maas}"

echo "=== DESTROYING ALL RKE2 WINDOWS EVAL RESOURCES ==="
echo ""
echo "This will delete:"
echo "  - VM 200 (rancher-mgmt)"
echo "  - VM 201 (windows-worker)"
echo "  - VM 202 (linux-control)"
echo "  - All cluster state in Rancher"
echo ""
read -p "Type 'destroy' to confirm: " CONFIRM
if [[ "$CONFIRM" != "destroy" ]]; then
    echo "Aborted."
    exit 1
fi

echo ""
echo "=== Stopping and destroying VMs ==="

for VMID in 200 201 202; do
    echo "Destroying VM $VMID..."
    ssh root@${PROXMOX_HOST} "qm stop $VMID 2>/dev/null || true; qm destroy $VMID --purge 2>/dev/null || true"
done

echo ""
echo "=== Removing DNS entry ==="
echo "NOTE: Manually remove 'rancher.homelab' from OPNsense if needed"

echo ""
echo "=== Cleanup complete ==="
echo "Run ./00-download-isos.sh to start fresh"
