#!/bin/bash
# Tune K3s VM for etcd performance
# Usage: ./tune-k3s-vm.sh <proxmox_host> <vmid> <disk_spec>
# Example: ./tune-k3s-vm.sh still-fawn.maas 108 "local-2TB-zfs:vm-108-disk-0,size=700G"

set -e

PROXMOX_HOST=$1
VMID=$2
DISK_SPEC=$3

if [[ -z "$PROXMOX_HOST" || -z "$VMID" || -z "$DISK_SPEC" ]]; then
    echo "Usage: $0 <proxmox_host> <vmid> <disk_spec>"
    echo "Example: $0 still-fawn.maas 108 'local-2TB-zfs:vm-108-disk-0,size=700G'"
    exit 1
fi

echo "=== Tuning VM $VMID on $PROXMOX_HOST ==="

# Step 1: Apply sysctl tuning
echo "Step 1: Applying sysctl tuning..."
ssh root@$PROXMOX_HOST "qm guest exec $VMID -- bash -c 'cat > /etc/sysctl.d/99-etcd.conf << EOF
# etcd performance tuning
vm.swappiness=10
vm.dirty_ratio=5
vm.dirty_background_ratio=3
EOF
sysctl -p /etc/sysctl.d/99-etcd.conf'"

# Step 2: Enable disk cache and iothread
echo "Step 2: Enabling disk cache and iothread..."
ssh root@$PROXMOX_HOST "qm set $VMID -scsi0 ${DISK_SPEC},cache=writeback,iothread=1"

# Step 3: Reboot VM
echo "Step 3: Rebooting VM..."
ssh root@$PROXMOX_HOST "qm reboot $VMID"

# Step 4: Wait for VM to come back
echo "Step 4: Waiting 60s for VM to reboot..."
sleep 60

# Step 5: Verify cluster health
echo "Step 5: Verifying cluster health..."
KUBECONFIG=~/kubeconfig kubectl get nodes -o wide

# Step 6: Verify config applied
echo "Step 6: Verifying disk config..."
ssh root@$PROXMOX_HOST "qm config $VMID | grep scsi0"

echo "Step 7: Verifying sysctl..."
ssh root@$PROXMOX_HOST "qm guest exec $VMID -- sysctl vm.swappiness vm.dirty_ratio vm.dirty_background_ratio"

echo "=== VM $VMID tuning complete ==="
