#!/bin/bash
# Recreate the windows-eval cluster completely
# This is the nuclear option after IPv6 issues corrupted the cluster state
set -e

PROXMOX_HOST="${PROXMOX_HOST:-pumped-piglet.maas}"
RANCHER_VM_IP="${RANCHER_VM_IP:-192.168.4.200}"
LINUX_VM_IP="${LINUX_VM_IP:-192.168.4.202}"
CLUSTER_NAME="windows-eval"

echo "=== Recreating Windows-Eval Cluster ==="
echo ""
echo "This will completely delete and recreate the cluster."
echo "Press Ctrl+C to abort, or wait 5 seconds..."
sleep 5

# 1. Delete the cluster
echo ""
echo "=== Step 1: Delete existing cluster ==="
ssh root@${PROXMOX_HOST} "ssh ubuntu@${RANCHER_VM_IP} 'sudo /var/lib/rancher/rke2/bin/kubectl --kubeconfig /etc/rancher/rke2/rke2.yaml delete clusters.provisioning.cattle.io ${CLUSTER_NAME} -n fleet-default'" 2>/dev/null || true

# Wait for deletion
echo "Waiting for cluster deletion..."
sleep 30

# 2. Clean up Linux node
echo ""
echo "=== Step 2: Clean up Linux node ==="
ssh root@${PROXMOX_HOST} "ssh ubuntu@${LINUX_VM_IP} 'sudo systemctl stop rancher-system-agent 2>/dev/null; sudo systemctl stop rke2-server 2>/dev/null; sudo systemctl stop rke2-agent 2>/dev/null; sudo rm -rf /var/lib/rancher/agent /etc/rancher/agent; echo done'" 2>/dev/null || true

# 3. Clean up Windows node
echo ""
echo "=== Step 3: Clean up Windows node ==="
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"${SCRIPT_DIR}/17-cleanup-windows-node.sh" 2>/dev/null || true

echo ""
echo "=== MANUAL STEP REQUIRED ==="
echo ""
echo "You need to:"
echo "1. Open Rancher UI: https://rancher.homelab"
echo "2. Create new cluster:"
echo "   - Name: windows-eval"
echo "   - CNI: Calico"
echo "   - Kubernetes Version: v1.34.x"
echo "3. Get the registration commands for:"
echo "   - Linux (etcd, controlplane, worker)"
echo "   - Windows (worker)"
echo ""
echo "When you have the new registration commands, update:"
echo "  - 08-register-linux-node.sh (with new token/checksum)"
echo "  - 09-register-windows-node.sh (with new token/checksum)"
echo ""
echo "Then run:"
echo "  ./08-register-linux-node.sh"
echo "  # Wait for Linux to be Ready"
echo "  ./09-register-windows-node.sh"
