#!/bin/bash
# Create and install Rancher on a VM (adapts to office environment)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Configuration - override with environment variables
PROXMOX_HOST="${PROXMOX_HOST:-}"
RANCHER_IP="${RANCHER_IP:-}"
RANCHER_HOSTNAME="${RANCHER_HOSTNAME:-rancher.office.local}"
VM_CORES="${VM_CORES:-2}"
VM_MEMORY="${VM_MEMORY:-4096}"
VM_DISK="${VM_DISK:-50G}"
STORAGE="${STORAGE:-local-lvm}"

usage() {
    cat <<EOF
Usage: $0 [OPTIONS]

Create Rancher management VM and install RKE2 + Rancher.

Options:
  --proxmox-host HOST   Proxmox host to create VM on
  --ip IP               IP address for Rancher VM (e.g., 192.168.1.200)
  --hostname NAME       Rancher hostname (default: rancher.office.local)
  --storage POOL        Proxmox storage pool (default: local-lvm)
  --cores N             CPU cores (default: 2)
  --memory MB           RAM in MB (default: 4096)
  --disk SIZE           Disk size (default: 50G)
  -h, --help            Show this help

Example:
  $0 --proxmox-host pve.office.local \\
     --ip 192.168.1.200 \\
     --hostname rancher.office.local

Prerequisites:
  - Ubuntu cloud image in /var/lib/vz/template/iso/
  - Network bridge configured
  - SSH key on Proxmox host

EOF
    exit 0
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --proxmox-host) PROXMOX_HOST="$2"; shift 2 ;;
        --ip) RANCHER_IP="$2"; shift 2 ;;
        --hostname) RANCHER_HOSTNAME="$2"; shift 2 ;;
        --storage) STORAGE="$2"; shift 2 ;;
        --cores) VM_CORES="$2"; shift 2 ;;
        --memory) VM_MEMORY="$2"; shift 2 ;;
        --disk) VM_DISK="$2"; shift 2 ;;
        -h|--help) usage ;;
        *) echo "Unknown option: $1"; usage ;;
    esac
done

if [[ -z "$PROXMOX_HOST" || -z "$RANCHER_IP" ]]; then
    echo "ERROR: --proxmox-host and --ip are required"
    usage
fi

# Detect gateway from IP
GATEWAY=$(echo "$RANCHER_IP" | sed 's/\.[0-9]*$/.1/')

echo "=== Creating Rancher VM on ${PROXMOX_HOST} ==="
echo ""
echo "IP:       ${RANCHER_IP}"
echo "Gateway:  ${GATEWAY}"
echo "Hostname: ${RANCHER_HOSTNAME}"
echo "Storage:  ${STORAGE}"
echo ""

# Find next available VMID
VMID=$(ssh root@${PROXMOX_HOST} "pvesh get /cluster/nextid")
echo "Using VMID: ${VMID}"

# Cloud image
CLOUD_IMAGE="noble-server-cloudimg-amd64.img"
CLOUD_IMAGE_URL="https://cloud-images.ubuntu.com/noble/current/${CLOUD_IMAGE}"

echo ""
echo "=== Checking for Ubuntu cloud image ==="
ssh root@${PROXMOX_HOST} "
    cd /var/lib/vz/template/iso/
    if [[ ! -f ${CLOUD_IMAGE} ]]; then
        echo 'Downloading Ubuntu 24.04 cloud image...'
        wget -q ${CLOUD_IMAGE_URL}
    else
        echo 'Cloud image exists'
    fi
"

echo ""
echo "=== Creating VM ${VMID} ==="
ssh root@${PROXMOX_HOST} "
    qm create ${VMID} --name rancher-mgmt --cores ${VM_CORES} --memory ${VM_MEMORY} \
        --net0 virtio,bridge=vmbr0 \
        --agent 1 \
        --ostype l26 \
        --cpu host \
        --scsihw virtio-scsi-pci

    qm importdisk ${VMID} /var/lib/vz/template/iso/${CLOUD_IMAGE} ${STORAGE}
    qm set ${VMID} --scsi0 ${STORAGE}:vm-${VMID}-disk-0,cache=writeback,discard=on
    qm set ${VMID} --boot order=scsi0
    qm resize ${VMID} scsi0 ${VM_DISK}

    qm set ${VMID} --ide2 ${STORAGE}:cloudinit
    qm set ${VMID} --ciuser ubuntu
    qm set ${VMID} --cipassword ubuntu123
    qm set ${VMID} --ipconfig0 ip=${RANCHER_IP}/24,gw=${GATEWAY}

    if [[ -f /root/.ssh/authorized_keys ]]; then
        qm set ${VMID} --sshkeys /root/.ssh/authorized_keys
    fi

    qm set ${VMID} --onboot 1
"

echo ""
echo "Starting VM..."
ssh root@${PROXMOX_HOST} "qm start ${VMID}"

echo ""
echo "=== Waiting for VM to boot ==="
for i in {1..60}; do
    if ssh root@${PROXMOX_HOST} "ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 ubuntu@${RANCHER_IP} uptime" 2>/dev/null; then
        echo "VM is ready!"
        break
    fi
    echo -n "."
    sleep 5
done
echo ""

echo "=== Installing RKE2 Server ==="
ssh root@${PROXMOX_HOST} "ssh ubuntu@${RANCHER_IP} 'curl -sfL https://get.rke2.io | sudo sh -'"
ssh root@${PROXMOX_HOST} "ssh ubuntu@${RANCHER_IP} 'sudo systemctl enable rke2-server && sudo systemctl start rke2-server'"

echo "Waiting for RKE2 to be ready..."
until ssh root@${PROXMOX_HOST} "ssh ubuntu@${RANCHER_IP} 'sudo /var/lib/rancher/rke2/bin/kubectl --kubeconfig /etc/rancher/rke2/rke2.yaml get nodes 2>/dev/null | grep -q Ready'"; do
    sleep 10
    echo -n "."
done
echo ""
echo "RKE2 is ready!"

echo ""
echo "=== Setting up kubectl ==="
ssh root@${PROXMOX_HOST} "ssh ubuntu@${RANCHER_IP} 'mkdir -p ~/.kube && sudo cp /etc/rancher/rke2/rke2.yaml ~/.kube/config && sudo chown \$(id -u):\$(id -g) ~/.kube/config'"
ssh root@${PROXMOX_HOST} "ssh ubuntu@${RANCHER_IP} 'echo export PATH=\\\$PATH:/var/lib/rancher/rke2/bin >> ~/.bashrc'"

echo ""
echo "=== Installing Helm ==="
ssh root@${PROXMOX_HOST} "ssh ubuntu@${RANCHER_IP} 'curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash'"

echo ""
echo "=== Installing cert-manager ==="
ssh root@${PROXMOX_HOST} "ssh ubuntu@${RANCHER_IP} 'export PATH=\$PATH:/var/lib/rancher/rke2/bin && helm repo add jetstack https://charts.jetstack.io && helm repo update'"
ssh root@${PROXMOX_HOST} "ssh ubuntu@${RANCHER_IP} 'export PATH=\$PATH:/var/lib/rancher/rke2/bin && kubectl create namespace cert-manager || true'"
ssh root@${PROXMOX_HOST} "ssh ubuntu@${RANCHER_IP} 'export PATH=\$PATH:/var/lib/rancher/rke2/bin && helm install cert-manager jetstack/cert-manager --namespace cert-manager --set installCRDs=true --wait'"

echo ""
echo "=== Installing Rancher ==="
ssh root@${PROXMOX_HOST} "ssh ubuntu@${RANCHER_IP} 'export PATH=\$PATH:/var/lib/rancher/rke2/bin && helm repo add rancher-latest https://releases.rancher.com/server-charts/latest && helm repo update'"
ssh root@${PROXMOX_HOST} "ssh ubuntu@${RANCHER_IP} 'export PATH=\$PATH:/var/lib/rancher/rke2/bin && kubectl create namespace cattle-system || true'"
ssh root@${PROXMOX_HOST} "ssh ubuntu@${RANCHER_IP} 'export PATH=\$PATH:/var/lib/rancher/rke2/bin && helm install rancher rancher-latest/rancher --namespace cattle-system --set hostname=${RANCHER_HOSTNAME} --set bootstrapPassword=admin --set replicas=1 --wait'"
ssh root@${PROXMOX_HOST} "ssh ubuntu@${RANCHER_IP} 'export PATH=\$PATH:/var/lib/rancher/rke2/bin && kubectl -n cattle-system rollout status deploy/rancher'"

echo ""
echo "=== Rancher Installation Complete ==="
echo ""
echo "VMID:              ${VMID}"
echo "Rancher URL:       https://${RANCHER_HOSTNAME}"
echo "Bootstrap password: admin"
echo ""
echo "Next steps:"
echo "1. Add DNS: ${RANCHER_HOSTNAME} → ${RANCHER_IP}"
echo "2. Access Rancher UI, create cluster with Calico CNI"
echo "3. Run ./03-install-rke2-agent-native.sh on Proxmox host"
echo "4. Run ./04-create-windows-vm.sh for Windows worker"
