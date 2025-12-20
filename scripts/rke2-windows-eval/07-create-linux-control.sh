#!/bin/bash
# Create Ubuntu 24.04 VM for RKE2 control plane on pumped-piglet
set -e

PROXMOX_HOST="pumped-piglet.maas"
VMID=202
VM_NAME="linux-control"
CORES=2
MEMORY=4096
DISK_SIZE="50G"
STORAGE="local-2TB-zfs"
BRIDGE="vmbr0"
IP="192.168.4.202"
GATEWAY="192.168.4.1"

CLOUD_IMAGE_NAME="noble-server-cloudimg-amd64.img"

echo "=== Creating Linux Control Plane VM on ${PROXMOX_HOST} ==="
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
    exit 1
fi

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
    qm set ${VMID} --cipassword ubuntu123
    qm set ${VMID} --ipconfig0 ip=${IP}/24,gw=${GATEWAY}
    qm set ${VMID} --nameserver 192.168.4.1
    qm set ${VMID} --searchdomain maas

    # Add SSH public key (use id_rsa.pub, not authorized_keys which may have restrictive options)
    if [[ -f /root/.ssh/id_rsa.pub ]]; then
        qm set ${VMID} --sshkeys /root/.ssh/id_rsa.pub
    fi

    # Start on boot
    qm set ${VMID} --onboot 1
"

# Create cloud-init user-data that disables IPv6 AND includes SSH key
# NOTE: When using cicustom, we must include everything in the custom file
# because it overrides the Proxmox-generated cloud-init
echo "Configuring cloud-init (IPv6 disable + SSH keys)..."
ssh root@${PROXMOX_HOST} "
    mkdir -p /var/lib/vz/snippets
    SSH_KEY=\$(cat /root/.ssh/id_rsa.pub)
    cat > /var/lib/vz/snippets/linux-control-user.yaml << CLOUDINIT
#cloud-config
# Custom cloud-init for RKE2 Linux control plane
# Disables IPv6 - critical for Rancher to use IPv4 address

user: ubuntu
password: ubuntu123
chpasswd:
  expire: false
ssh_pwauth: true

ssh_authorized_keys:
  - \${SSH_KEY}

bootcmd:
  - sysctl -w net.ipv6.conf.all.disable_ipv6=1
  - sysctl -w net.ipv6.conf.default.disable_ipv6=1

runcmd:
  - echo 'net.ipv6.conf.all.disable_ipv6 = 1' >> /etc/sysctl.conf
  - echo 'net.ipv6.conf.default.disable_ipv6 = 1' >> /etc/sysctl.conf
  - sysctl -p
CLOUDINIT

    qm set ${VMID} --cicustom 'user=local:snippets/linux-control-user.yaml'
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
echo "2. In Rancher UI: Create cluster with Calico CNI"
echo "3. Get Linux registration command"
echo "4. Run: ./08-register-linux-node.sh '<registration-command>'"
