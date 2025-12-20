#!/bin/bash
# Check Rancher health and diagnose 503 errors
set -e

PROXMOX_HOST="pumped-piglet.maas"
RANCHER_VM_IP="192.168.4.200"
RANCHER_URL="https://rancher.homelab"

echo "=== Rancher Health Check ==="
echo ""

echo "=== HTTP Status ==="
for i in 1 2 3; do
    HTTP_CODE=$(curl -sk -o /dev/null -w "%{http_code}" ${RANCHER_URL}/)
    echo "Attempt $i: HTTP $HTTP_CODE"
    if [ "$HTTP_CODE" = "200" ]; then
        echo "Rancher is UP"
        break
    fi
    sleep 2
done
echo ""

echo "=== VM Resources ==="
ssh root@${PROXMOX_HOST} "ssh ubuntu@${RANCHER_VM_IP} 'free -h && echo \"\" && uptime'"
echo ""

echo "=== Rancher Pods ==="
ssh root@${PROXMOX_HOST} "ssh ubuntu@${RANCHER_VM_IP} '
    export PATH=\$PATH:/var/lib/rancher/rke2/bin
    export KUBECONFIG=~/.kube/config
    kubectl get pods -n cattle-system
'"
echo ""

echo "=== Ingress Controller ==="
ssh root@${PROXMOX_HOST} "ssh ubuntu@${RANCHER_VM_IP} '
    export PATH=\$PATH:/var/lib/rancher/rke2/bin
    export KUBECONFIG=~/.kube/config
    kubectl get pods -n kube-system | grep ingress
'"
echo ""

echo "=== Recent Rancher Logs ==="
ssh root@${PROXMOX_HOST} "ssh ubuntu@${RANCHER_VM_IP} '
    export PATH=\$PATH:/var/lib/rancher/rke2/bin
    export KUBECONFIG=~/.kube/config
    kubectl logs -n cattle-system deployment/rancher --tail=10
'"
