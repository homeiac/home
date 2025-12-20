#!/bin/bash
# Check Rancher status and diagnose issues
set -e

PROXMOX_HOST="pumped-piglet.maas"
RANCHER_VM_IP="192.168.4.200"

echo "=== Rancher Status Check ==="
echo ""

ssh root@${PROXMOX_HOST} "ssh -o StrictHostKeyChecking=no ubuntu@${RANCHER_VM_IP} '
    export PATH=\$PATH:/var/lib/rancher/rke2/bin
    export KUBECONFIG=~/.kube/config

    echo \"=== RKE2 Node Status ===\"
    kubectl get nodes
    echo ""

    echo \"=== Rancher Pods ===\"
    kubectl get pods -n cattle-system | grep -v helm-operation
    echo ""

    echo \"=== Ingress Controller ===\"
    kubectl get pods -n kube-system | grep ingress
    echo ""

    echo \"=== Rancher Ingress ===\"
    kubectl get ingress -n cattle-system
    echo ""

    echo \"=== Test Rancher API (with Host header) ===\"
    HTTP_CODE=\$(curl -sk -o /dev/null -w \"%{http_code}\" -H \"Host: rancher.homelab\" https://127.0.0.1/)
    if [ \"\$HTTP_CODE\" = \"200\" ]; then
        echo \"Rancher API responding: HTTP \$HTTP_CODE\"
    else
        echo \"WARNING: Rancher API returned HTTP \$HTTP_CODE\"
    fi
    echo ""

    echo \"=== Test from external (your browser needs this) ===\"
    echo \"DNS: rancher.homelab should resolve to ${RANCHER_VM_IP}\"
    echo \"URL: https://rancher.homelab\"
    echo \"Bootstrap password: admin\"
'"

echo ""
echo "If you get 404 in browser, check:"
echo "1. DNS entry exists in OPNsense for rancher.homelab -> ${RANCHER_VM_IP}"
echo "2. Browser is sending correct Host header (try incognito mode)"
echo "3. No proxy/VPN interfering"
