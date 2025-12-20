#!/bin/bash
# Start RKE2 cluster VMs
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/.env" 2>/dev/null || true

PROXMOX_HOST="${PROXMOX_HOST:-pumped-piglet.maas}"

echo "=== Starting RKE2 Cluster VMs ==="
echo ""

# Start in order: management first, then control plane, then workers
for VMID in 200 202 201; do
    VM_NAME=$(ssh root@${PROXMOX_HOST} "qm config ${VMID} 2>/dev/null | grep '^name:' | cut -d' ' -f2" || echo "unknown")
    STATUS=$(ssh root@${PROXMOX_HOST} "qm status ${VMID} 2>/dev/null | awk '{print \$2}'" || echo "unknown")

    if [[ "$STATUS" == "stopped" ]]; then
        echo "Starting VM ${VMID} (${VM_NAME})..."
        ssh root@${PROXMOX_HOST} "qm start ${VMID}"
    else
        echo "VM ${VMID} (${VM_NAME}) already running"
    fi
done

echo ""
echo "=== VMs Started ==="
echo ""
echo "Waiting for cluster to be ready..."
sleep 30

echo ""
ssh root@${PROXMOX_HOST} "qm list"
echo ""
echo "Check cluster status: ./22-check-rancher-status.sh"
