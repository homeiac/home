#!/bin/bash
# Install Rancher on RKE2 cluster (run after ingress is ready)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/.env" 2>/dev/null || true

PROXMOX_HOST="${PROXMOX_HOST:-pumped-piglet.maas}"
RANCHER_VM_IP="${RANCHER_VM_IP:-192.168.4.200}"
RANCHER_HOSTNAME="${RANCHER_HOSTNAME:-rancher.homelab}"

echo "=== Installing Rancher ==="
echo ""
echo "Rancher VM: ${RANCHER_VM_IP}"
echo "Rancher hostname: ${RANCHER_HOSTNAME}"
echo ""

# Install Rancher via Helm
ssh root@${PROXMOX_HOST} "ssh ubuntu@${RANCHER_VM_IP} '
    export KUBECONFIG=~/.kube/config

    # Add Rancher Helm repo if not already added
    helm repo add rancher-latest https://releases.rancher.com/server-charts/latest 2>/dev/null || true
    helm repo update

    # Check if rancher namespace exists
    if ! kubectl get namespace cattle-system 2>/dev/null; then
        kubectl create namespace cattle-system
    fi

    # Install or upgrade Rancher
    helm upgrade --install rancher rancher-latest/rancher \\
        --namespace cattle-system \\
        --set hostname=${RANCHER_HOSTNAME} \\
        --set replicas=1 \\
        --set bootstrapPassword=admin \\
        --wait --timeout=10m
'"

echo ""
echo "=== Rancher Installation Complete ==="
echo ""
echo "Waiting for Rancher pods..."
ssh root@${PROXMOX_HOST} "ssh ubuntu@${RANCHER_VM_IP} 'kubectl get pods -n cattle-system'"

echo ""
echo "=== Next Steps ==="
echo ""
echo "1. Add DNS: rancher.homelab → ${RANCHER_VM_IP}"
echo "2. Access: https://${RANCHER_HOSTNAME}"
echo "3. Initial password: admin"
