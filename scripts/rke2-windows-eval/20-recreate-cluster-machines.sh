#!/bin/bash
# Recreate cluster machines with IPv4 only
# This deletes both machines and re-registers them
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/.env" ]]; then
    source "${SCRIPT_DIR}/.env"
fi

PROXMOX_HOST="${PROXMOX_HOST:-pumped-piglet.maas}"
RANCHER_VM_IP="${RANCHER_VM_IP:-192.168.4.200}"
LINUX_VM_IP="${LINUX_VM_IP:-192.168.4.202}"

echo "=== Recreating Cluster Machines with IPv4 ==="
echo ""
echo "This will:"
echo "1. Delete both machines from the windows-eval cluster"
echo "2. Cleanup Linux and Windows nodes"
echo "3. Re-register Linux (now IPv4-only)"
echo "4. Re-register Windows"
echo ""
read -p "Continue? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
fi

# 1. Delete machines from Rancher
echo ""
echo "=== Deleting machines from Rancher ==="
ssh root@${PROXMOX_HOST} "ssh ubuntu@${RANCHER_VM_IP} 'sudo /var/lib/rancher/rke2/bin/kubectl --kubeconfig /etc/rancher/rke2/rke2.yaml delete machine --all -n fleet-default'" || true

# 2. Cleanup Linux node
echo ""
echo "=== Cleaning up Linux node ==="
ssh root@${PROXMOX_HOST} "ssh ubuntu@${LINUX_VM_IP} 'sudo systemctl stop rancher-system-agent 2>/dev/null || true; sudo rm -rf /var/lib/rancher/agent 2>/dev/null || true'"

# 3. Cleanup Windows node (using the cleanup script)
echo ""
echo "=== Cleaning up Windows node ==="
"${SCRIPT_DIR}/17-cleanup-windows-node.sh" || true

# 4. Re-register Linux
echo ""
echo "=== Re-registering Linux node ==="
"${SCRIPT_DIR}/08-register-linux-node.sh"

# 5. Wait for Linux to be ready
echo ""
echo "Waiting for Linux node to be Ready..."
for i in {1..30}; do
    STATUS=$(ssh root@${PROXMOX_HOST} "ssh ubuntu@${RANCHER_VM_IP} 'sudo /var/lib/rancher/rke2/bin/kubectl --kubeconfig /etc/rancher/rke2/rke2.yaml get machines.cluster.x-k8s.io -n fleet-default -o jsonpath=\"{.items[0].status.phase}\"'" 2>/dev/null || echo "NotFound")
    echo "  Machine status: $STATUS"
    if [[ "$STATUS" == "Running" ]]; then
        echo "Linux node is Ready!"
        break
    fi
    sleep 10
done

# 6. Check the Linux machine's address
echo ""
echo "=== Verifying Linux machine uses IPv4 ==="
ssh root@${PROXMOX_HOST} "ssh ubuntu@${RANCHER_VM_IP} 'sudo /var/lib/rancher/rke2/bin/kubectl --kubeconfig /etc/rancher/rke2/rke2.yaml get machines.cluster.x-k8s.io -n fleet-default -o yaml'" 2>/dev/null | grep -A5 "addresses" | head -10

# 7. Re-register Windows
echo ""
echo "=== Re-registering Windows node ==="
"${SCRIPT_DIR}/09-register-windows-node.sh"

echo ""
echo "=== Done ==="
echo "Monitor Windows node with: ./18-check-windows-status.sh"
