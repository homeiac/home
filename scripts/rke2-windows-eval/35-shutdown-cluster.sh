#!/bin/bash
# Shutdown RKE2 cluster VMs (preserves state for later restart)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/.env" 2>/dev/null || true

PROXMOX_HOST="${PROXMOX_HOST:-pumped-piglet.maas}"

echo "=== Shutting Down RKE2 Cluster VMs ==="
echo ""

# Shutdown in reverse order: workers first, then control plane, then management
for VMID in 201 202 200; do
    VM_NAME=$(ssh root@${PROXMOX_HOST} "qm config ${VMID} 2>/dev/null | grep '^name:' | cut -d' ' -f2" || echo "unknown")
    STATUS=$(ssh root@${PROXMOX_HOST} "qm status ${VMID} 2>/dev/null | awk '{print \$2}'" || echo "unknown")

    if [[ "$STATUS" == "running" ]]; then
        echo "Stopping VM ${VMID} (${VM_NAME})..."
        ssh root@${PROXMOX_HOST} "qm shutdown ${VMID} --timeout 60 2>/dev/null || qm stop ${VMID}"
    else
        echo "VM ${VMID} (${VM_NAME}) already stopped"
    fi
done

echo ""
echo "=== Cluster Shutdown Complete ==="
echo ""
ssh root@${PROXMOX_HOST} "qm list"
echo ""
echo "To restart: ./36-start-cluster.sh"
