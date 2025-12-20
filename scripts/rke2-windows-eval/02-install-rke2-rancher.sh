#!/bin/bash
# Install RKE2 and Rancher on the rancher-server VM
set -e

PROXMOX_HOST="pumped-piglet.maas"
RANCHER_VM_IP="192.168.4.200"
RANCHER_HOSTNAME="rancher.homelab"

echo "=== Installing RKE2 + Rancher on ${RANCHER_VM_IP} ==="
echo ""

# Check SSH connectivity
if ! ssh root@${PROXMOX_HOST} "ssh -o StrictHostKeyChecking=no ubuntu@${RANCHER_VM_IP} uptime" 2>/dev/null; then
    echo "ERROR: Cannot SSH to ubuntu@${RANCHER_VM_IP} via ${PROXMOX_HOST}"
    echo "Ensure VM is running and cloud-init completed"
    exit 1
fi

echo "Installing RKE2 server..."
ssh root@${PROXMOX_HOST} "ssh ubuntu@${RANCHER_VM_IP} 'curl -sfL https://get.rke2.io | sudo sh -'"
ssh root@${PROXMOX_HOST} "ssh ubuntu@${RANCHER_VM_IP} 'sudo systemctl enable rke2-server && sudo systemctl start rke2-server'"

echo "Waiting for RKE2 to be ready (this takes a few minutes)..."
until ssh root@${PROXMOX_HOST} "ssh ubuntu@${RANCHER_VM_IP} 'sudo /var/lib/rancher/rke2/bin/kubectl --kubeconfig /etc/rancher/rke2/rke2.yaml get nodes 2>/dev/null | grep -q Ready'"; do
    sleep 10
    echo "  Still waiting..."
done
echo "RKE2 is ready!"

echo "Setting up kubectl for ubuntu user..."
ssh root@${PROXMOX_HOST} "ssh ubuntu@${RANCHER_VM_IP} 'mkdir -p ~/.kube && sudo cp /etc/rancher/rke2/rke2.yaml ~/.kube/config && sudo chown \$(id -u):\$(id -g) ~/.kube/config'"
ssh root@${PROXMOX_HOST} "ssh ubuntu@${RANCHER_VM_IP} 'echo export PATH=\\\$PATH:/var/lib/rancher/rke2/bin >> ~/.bashrc'"
ssh root@${PROXMOX_HOST} "ssh ubuntu@${RANCHER_VM_IP} 'export PATH=\$PATH:/var/lib/rancher/rke2/bin && kubectl get nodes'"

echo ""
echo "Installing Helm..."
ssh root@${PROXMOX_HOST} "ssh ubuntu@${RANCHER_VM_IP} 'curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash'"

echo ""
echo "Installing cert-manager..."
ssh root@${PROXMOX_HOST} "ssh ubuntu@${RANCHER_VM_IP} 'export PATH=\$PATH:/var/lib/rancher/rke2/bin && helm repo add jetstack https://charts.jetstack.io && helm repo update'"
ssh root@${PROXMOX_HOST} "ssh ubuntu@${RANCHER_VM_IP} 'export PATH=\$PATH:/var/lib/rancher/rke2/bin && kubectl create namespace cert-manager || true'"
ssh root@${PROXMOX_HOST} "ssh ubuntu@${RANCHER_VM_IP} 'export PATH=\$PATH:/var/lib/rancher/rke2/bin && helm install cert-manager jetstack/cert-manager --namespace cert-manager --set installCRDs=true --wait'"
ssh root@${PROXMOX_HOST} "ssh ubuntu@${RANCHER_VM_IP} 'export PATH=\$PATH:/var/lib/rancher/rke2/bin && kubectl get pods -n cert-manager'"

echo ""
echo "Installing Rancher..."
ssh root@${PROXMOX_HOST} "ssh ubuntu@${RANCHER_VM_IP} 'export PATH=\$PATH:/var/lib/rancher/rke2/bin && helm repo add rancher-latest https://releases.rancher.com/server-charts/latest && helm repo update'"
ssh root@${PROXMOX_HOST} "ssh ubuntu@${RANCHER_VM_IP} 'export PATH=\$PATH:/var/lib/rancher/rke2/bin && kubectl create namespace cattle-system || true'"
ssh root@${PROXMOX_HOST} "ssh ubuntu@${RANCHER_VM_IP} 'export PATH=\$PATH:/var/lib/rancher/rke2/bin && helm install rancher rancher-latest/rancher --namespace cattle-system --set hostname=${RANCHER_HOSTNAME} --set bootstrapPassword=admin --set replicas=1 --wait'"
ssh root@${PROXMOX_HOST} "ssh ubuntu@${RANCHER_VM_IP} 'export PATH=\$PATH:/var/lib/rancher/rke2/bin && kubectl -n cattle-system rollout status deploy/rancher'"
ssh root@${PROXMOX_HOST} "ssh ubuntu@${RANCHER_VM_IP} 'export PATH=\$PATH:/var/lib/rancher/rke2/bin && kubectl get pods -n cattle-system'"

echo ""
echo "=== Rancher Installation Complete ==="
echo ""
echo "Access Rancher at: https://${RANCHER_HOSTNAME}"
echo "Bootstrap password: admin"
echo ""
echo "Next steps:"
echo "1. Create cluster in Rancher UI with Calico CNI"
echo "2. Run ./07-create-linux-control.sh"
echo "3. Register Linux node, then Windows node"
