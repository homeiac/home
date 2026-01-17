#!/bin/bash
# Join a VM to the K3s cluster as a server (control-plane) node
#
# Usage: ./join-server.sh <VM_IP> [K3S_VERSION]
#
# Prerequisites:
# - VM must be running and accessible via SSH as ubuntu@<VM_IP>
# - kubectl must be configured to access the K3s cluster
# - K3s token Secret must exist in cluster
#
# The script reads the K3s join token from a Kubernetes Secret,
# keeping secrets out of Git and cloud-init snippets.

set -e

VM_IP="${1:-}"
K3S_VERSION="${2:-v1.33.6+k3s1}"
K3S_SERVER_URL="https://192.168.4.210:6443"
SECRET_NAME="k3s-join-token"
SECRET_NAMESPACE="crossplane-system"

if [[ -z "$VM_IP" ]]; then
    echo "Usage: $0 <VM_IP> [K3S_VERSION]"
    echo ""
    echo "Example: $0 192.168.4.201"
    echo "         $0 192.168.4.201 v1.33.6+k3s1"
    exit 1
fi

echo "=== K3s Server Join Script ==="
echo "VM IP: $VM_IP"
echo "K3s Version: $K3S_VERSION"
echo "Server URL: $K3S_SERVER_URL"
echo ""

# Read token from Kubernetes Secret
echo "Reading K3s token from Secret ${SECRET_NAMESPACE}/${SECRET_NAME}..."
K3S_TOKEN=$(kubectl get secret "$SECRET_NAME" -n "$SECRET_NAMESPACE" -o jsonpath='{.data.token}' 2>/dev/null | base64 -d)

if [[ -z "$K3S_TOKEN" ]]; then
    echo "ERROR: Could not read K3s token from Secret"
    echo ""
    echo "Create the secret with:"
    echo "  kubectl create secret generic $SECRET_NAME -n $SECRET_NAMESPACE --from-literal=token=<TOKEN>"
    echo ""
    echo "Or get the token from an existing control-plane node:"
    echo "  ssh root@pumped-piglet.maas 'qm guest exec 105 -- cat /var/lib/rancher/k3s/server/node-token'"
    exit 1
fi

echo "Token retrieved successfully"
echo ""

# Test SSH connectivity
echo "Testing SSH connectivity to $VM_IP..."
if ! ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 ubuntu@"$VM_IP" "echo 'SSH OK'" 2>/dev/null; then
    echo "ERROR: Cannot SSH to ubuntu@$VM_IP"
    echo "Ensure the VM is running and cloud-init has completed"
    exit 1
fi

echo "SSH connection successful"
echo ""

# Install K3s
echo "Installing K3s on $VM_IP..."
ssh -o StrictHostKeyChecking=no ubuntu@"$VM_IP" "curl -sfL https://get.k3s.io | \
    K3S_URL='$K3S_SERVER_URL' \
    K3S_TOKEN='$K3S_TOKEN' \
    INSTALL_K3S_VERSION='$K3S_VERSION' \
    sudo sh -s - server --disable servicelb"

echo ""
echo "K3s installation initiated. Waiting for node to join..."
echo ""

# Wait for node to appear in cluster
for i in $(seq 1 30); do
    NODE_NAME=$(kubectl get nodes -o jsonpath='{.items[*].metadata.name}' 2>/dev/null | tr ' ' '\n' | grep -v "pumped-piglet\|pve" | head -1)
    if [[ -n "$NODE_NAME" ]]; then
        echo "Node joined: $NODE_NAME"
        kubectl get nodes
        exit 0
    fi
    echo "Waiting for node to join... ($i/30)"
    sleep 10
done

echo "WARNING: Node did not appear in cluster within 5 minutes"
echo "Check K3s logs on the VM: ssh ubuntu@$VM_IP 'sudo journalctl -u k3s -f'"
exit 1
