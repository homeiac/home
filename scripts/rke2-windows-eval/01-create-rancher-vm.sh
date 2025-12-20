#!/bin/bash
# Create Ubuntu 24.04 VM for Rancher server on pumped-piglet
set -e

PROXMOX_HOST="pumped-piglet.maas"
VMID=200
VM_NAME="rancher-mgmt"
CORES=2
MEMORY=4096
DISK_SIZE="50G"
STORAGE="local-2TB-zfs"  # ZFS storage on pumped-piglet
BRIDGE="vmbr0"
IP="192.168.4.200"
GATEWAY="192.168.4.1"

# Ubuntu cloud image
CLOUD_IMAGE_URL="https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img"
CLOUD_IMAGE_NAME="noble-server-cloudimg-amd64.img"

echo "=== Creating Rancher Server VM on ${PROXMOX_HOST} ==="
echo ""
echo "VM Configuration:"
echo "  VMID: ${VMID}"
echo "  Name: ${VM_NAME}"
echo "  CPU: ${CORES} cores"
echo "  RAM: ${MEMORY}MB"
echo "  Disk: ${DISK_SIZE}"
echo "  IP: ${IP}/24"
echo ""

# Check if VM already exists
if ssh root@${PROXMOX_HOST} "qm status ${VMID}" 2>/dev/null; then
    echo "ERROR: VM ${VMID} already exists on ${PROXMOX_HOST}"
    echo "Run ./99-cleanup.sh first or choose a different VMID"
    exit 1
fi

# Download cloud image if not present
echo "Checking for Ubuntu cloud image..."
ssh root@${PROXMOX_HOST} "
    cd /var/lib/vz/template/iso/
    if [[ ! -f ${CLOUD_IMAGE_NAME} ]]; then
        echo 'Downloading Ubuntu 24.04 cloud image...'
        wget -q ${CLOUD_IMAGE_URL}
    else
        echo 'Cloud image already exists'
    fi
"

# Create the VM
echo "Creating VM ${VMID}..."
ssh root@${PROXMOX_HOST} "
    # Create VM
    qm create ${VMID} --name ${VM_NAME} --cores ${CORES} --memory ${MEMORY} \
        --net0 virtio,bridge=${BRIDGE} \
        --agent 1 \
        --ostype l26 \
        --cpu host \
        --scsihw virtio-scsi-pci

    # Import cloud image as disk
    qm importdisk ${VMID} /var/lib/vz/template/iso/${CLOUD_IMAGE_NAME} ${STORAGE}

    # Attach disk and set boot order
    qm set ${VMID} --scsi0 ${STORAGE}:vm-${VMID}-disk-0,cache=writeback,discard=on,iothread=1
    qm set ${VMID} --boot order=scsi0

    # Resize disk
    qm resize ${VMID} scsi0 ${DISK_SIZE}

    # Add cloud-init drive
    qm set ${VMID} --ide2 ${STORAGE}:cloudinit

    # Configure cloud-init
    qm set ${VMID} --ciuser ubuntu
    qm set ${VMID} --cipassword ubuntu123  # Change this!
    qm set ${VMID} --ipconfig0 ip=${IP}/24,gw=${GATEWAY}
    qm set ${VMID} --nameserver 192.168.4.1
    qm set ${VMID} --searchdomain maas

    # Add SSH key if available
    if [[ -f /root/.ssh/authorized_keys ]]; then
        qm set ${VMID} --sshkeys /root/.ssh/authorized_keys
    fi

    # Start on boot
    qm set ${VMID} --onboot 1
"

echo ""
echo "VM ${VMID} created successfully!"
echo ""
echo "Starting VM..."
ssh root@${PROXMOX_HOST} "qm start ${VMID}"

echo ""
echo "=== Next Steps ==="
echo ""
echo "1. Wait for VM to boot (~1-2 minutes)"
echo "2. SSH to the VM: ssh ubuntu@${IP}"
echo "3. Run: ./02-install-rke2-rancher.sh"
echo ""
echo "Default credentials: ubuntu / ubuntu123"
echo "(Change the password immediately!)"
