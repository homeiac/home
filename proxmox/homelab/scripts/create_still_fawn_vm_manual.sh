#!/bin/bash
# Manual VM creation for still-fawn using qm commands via SSH
# This bypasses the Proxmox API SSL certificate issues

set -e

NODE="still-fawn.maas"
VMID=108
VM_NAME="k3s-vm-still-fawn"
CORES=3  # 80% of 4 cores
MEMORY=25595  # 80% of 31994MB
STORAGE="local-2TB-zfs"
ISO_PATH="/var/lib/vz/template/iso/noble-server-cloudimg-amd64.img"
DISK_SIZE="700G"  # Match existing config

# Cloud-init settings
CLOUD_USER="ubuntu"
CLOUD_PASSWORD="ubuntu"
SSH_KEY_PATH="/root/.ssh/id_rsa.pub"

echo "=========================================="
echo "Creating VM $VM_NAME on $NODE"
echo "=========================================="
echo "VMID: $VMID"
echo "Cores: $CORES"
echo "Memory: ${MEMORY}MB"
echo "Storage: $STORAGE"
echo "=========================================="

# Read SSH key
SSH_KEY=$(cat $SSH_KEY_PATH)

# Create VM on still-fawn
ssh root@$NODE "qm create $VMID \
  --name $VM_NAME \
  --cores $CORES \
  --memory $MEMORY \
  --net0 virtio,bridge=vmbr0 \
  --net1 virtio,bridge=vmbr1"

echo "✅ VM shell created"

# Import disk
ssh root@$NODE "qm importdisk $VMID $ISO_PATH $STORAGE"

echo "✅ Disk imported"

# Configure VM
ssh root@$NODE "qm set $VMID \
  --scsihw virtio-scsi-pci \
  --scsi0 $STORAGE:vm-$VMID-disk-0 \
  --ide2 $STORAGE:cloudinit \
  --boot c \
  --bootdisk scsi0 \
  --agent 1"

echo "✅ VM configured"

# Resize disk
ssh root@$NODE "qm resize $VMID scsi0 $DISK_SIZE"

echo "✅ Disk resized to $DISK_SIZE"

# Configure cloud-init (note: cicustom requires the snippet to exist)
ssh root@$NODE "qm set $VMID \
  --ciuser $CLOUD_USER \
  --cipassword $CLOUD_PASSWORD \
  --sshkeys '$SSH_KEY' \
  --ipconfig0 ip=dhcp"

echo "✅ Cloud-init configured"

# Start VM
ssh root@$NODE "qm start $VMID"

echo "✅ VM started"
echo ""
echo "=========================================="
echo "VM $VM_NAME created successfully!"
echo "=========================================="
echo "Wait a few minutes for cloud-init to complete"
echo "Then verify with: ssh ubuntu@$VM_NAME"
