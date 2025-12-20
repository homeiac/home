#!/bin/bash
# Recreate Linux control plane machine with IPv4 only
set -e

PROXMOX_HOST="${PROXMOX_HOST:-pumped-piglet.maas}"
RANCHER_VM_IP="${RANCHER_VM_IP:-192.168.4.200}"
LINUX_VM_IP="${LINUX_VM_IP:-192.168.4.202}"

echo "=== Recreating Linux Machine with IPv4 ==="
echo ""

# Get the machine name
LINUX_MACHINE=$(ssh root@${PROXMOX_HOST} "ssh ubuntu@${RANCHER_VM_IP} 'sudo /var/lib/rancher/rke2/bin/kubectl --kubeconfig /etc/rancher/rke2/rke2.yaml get machines.cluster.x-k8s.io -n fleet-default -o name | grep -v 1d789e'" 2>/dev/null | head -1)
echo "Linux machine: $LINUX_MACHINE"

# Delete the machine
echo ""
echo "Deleting Linux machine..."
ssh root@${PROXMOX_HOST} "ssh ubuntu@${RANCHER_VM_IP} 'sudo /var/lib/rancher/rke2/bin/kubectl --kubeconfig /etc/rancher/rke2/rke2.yaml delete ${LINUX_MACHINE} -n fleet-default'" || true

# Wait a moment
sleep 5

# Clean up Linux node's rancher-system-agent data
echo ""
echo "Cleaning up Linux node agent data..."
ssh root@${PROXMOX_HOST} "ssh ubuntu@${LINUX_VM_IP} 'sudo rm -rf /var/lib/rancher/agent/applied/*.plan 2>/dev/null; sudo systemctl restart rancher-system-agent'" || true

# Wait for machine to re-register
echo ""
echo "Waiting for Linux machine to re-register..."
for i in {1..30}; do
    MACHINES=$(ssh root@${PROXMOX_HOST} "ssh ubuntu@${RANCHER_VM_IP} 'sudo /var/lib/rancher/rke2/bin/kubectl --kubeconfig /etc/rancher/rke2/rke2.yaml get machines.cluster.x-k8s.io -n fleet-default -o wide 2>/dev/null'" 2>/dev/null || echo "error")
    echo "$MACHINES" | tail -2

    if echo "$MACHINES" | grep -q "linux-control.*Running"; then
        echo ""
        echo "Linux machine is Running!"
        break
    fi
    sleep 10
done

# Check the addresses
echo ""
echo "=== Checking machine addresses ==="
ssh root@${PROXMOX_HOST} "ssh ubuntu@${RANCHER_VM_IP} 'sudo /var/lib/rancher/rke2/bin/kubectl --kubeconfig /etc/rancher/rke2/rke2.yaml get machines.cluster.x-k8s.io -n fleet-default -o yaml'" 2>/dev/null | grep -A10 "addresses:" | head -15

echo ""
echo "=== Done ==="
