#!/bin/bash
# Wait for RKE2 ingress controller to be ready
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/.env" 2>/dev/null || true

PROXMOX_HOST="${PROXMOX_HOST:-pumped-piglet.maas}"
RANCHER_VM_IP="${RANCHER_VM_IP:-192.168.4.200}"
MAX_ATTEMPTS="${1:-60}"

echo "=== Waiting for RKE2 Ingress Controller ==="
echo ""
echo "Rancher VM: ${RANCHER_VM_IP}"
echo "Max attempts: ${MAX_ATTEMPTS} (5s intervals)"
echo ""

for i in $(seq 1 $MAX_ATTEMPTS); do
    STATUS=$(ssh root@${PROXMOX_HOST} "ssh ubuntu@${RANCHER_VM_IP} 'sudo /var/lib/rancher/rke2/bin/kubectl --kubeconfig /etc/rancher/rke2/rke2.yaml get pods -n kube-system -l app.kubernetes.io/component=controller -o jsonpath=\"{.items[0].status.phase}\"'" 2>/dev/null || echo "Unknown")

    if [[ "$STATUS" == "Running" ]]; then
        echo ""
        echo "✓ Ingress controller is Running!"
        exit 0
    fi

    echo "  Attempt $i/$MAX_ATTEMPTS: Status=$STATUS"
    sleep 5
done

echo ""
echo "ERROR: Ingress controller did not become ready after ${MAX_ATTEMPTS} attempts"
exit 1
