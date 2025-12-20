#!/bin/bash
# Check status of Rancher installation
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/.env" 2>/dev/null || true

PROXMOX_HOST="${PROXMOX_HOST:-pumped-piglet.maas}"
RANCHER_VM_IP="${RANCHER_VM_IP:-192.168.4.200}"

KUBECTL="sudo /var/lib/rancher/rke2/bin/kubectl --kubeconfig /etc/rancher/rke2/rke2.yaml"
SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=10"

run_kubectl() {
    ssh ${SSH_OPTS} root@${PROXMOX_HOST} "ssh ${SSH_OPTS} ubuntu@${RANCHER_VM_IP} '${KUBECTL} $1'" 2>/dev/null
}

echo "=== Rancher Cluster Status ==="
echo ""

# Node status
echo "--- Nodes ---"
run_kubectl "get nodes -o wide" || echo "Failed to get nodes"

echo ""
echo "--- Ingress Controller ---"
run_kubectl "get pods -n kube-system -l app.kubernetes.io/component=controller" || echo "Failed to get ingress"

echo ""
echo "--- Cert-Manager ---"
run_kubectl "get pods -n cert-manager" || echo "Failed to get cert-manager"

echo ""
echo "--- Rancher ---"
run_kubectl "get pods -n cattle-system" || echo "Rancher not yet installed"

echo ""
echo "--- Rancher Helm Release ---"
ssh ${SSH_OPTS} root@${PROXMOX_HOST} "ssh ${SSH_OPTS} ubuntu@${RANCHER_VM_IP} 'helm --kubeconfig ~/.kube/config list -n cattle-system'" 2>/dev/null || echo "No Helm release"

echo ""
echo "--- Bootstrap Password ---"
run_kubectl "get secret --namespace cattle-system bootstrap-secret -o go-template=\"{{.data.bootstrapPassword|base64decode}}\"" || echo "Not yet available"
