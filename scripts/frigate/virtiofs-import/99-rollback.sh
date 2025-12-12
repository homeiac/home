#!/bin/bash
#
# 99-rollback.sh
#
# Rollback virtiofs setup if issues occur
# WARNING: This will remove the virtiofs mount and optionally delete the dataset
#

set -euo pipefail

HOST="pumped-piglet.maas"
VMID="105"
VM_SSH="ubuntu@k3s-vm-pumped-piglet-gpu"
MAPPING_ID="frigate-import"
MOUNT_POINT="/mnt/frigate-import"
DATASET="local-3TB-backup/frigate-import"
KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "========================================="
echo "VirtioFS Rollback"
echo "========================================="
echo ""
echo -e "${RED}WARNING: This will undo the virtiofs setup${NC}"
echo ""
echo "This script will:"
echo "  1. Unmount virtiofs in VM"
echo "  2. Remove fstab entry"
echo "  3. Remove virtiofs device from VM (requires restart)"
echo "  4. Delete directory mapping"
echo "  5. Optionally delete the ZFS dataset (with copied data)"
echo ""
read -p "Continue with rollback? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted"
    exit 0
fi
echo ""

# Step 1: Unmount in VM
echo "Step 1: Unmounting virtiofs in VM..."
if ssh -o ConnectTimeout=10 $VM_SSH "mountpoint -q $MOUNT_POINT 2>/dev/null"; then
    ssh $VM_SSH "sudo umount $MOUNT_POINT" || echo "Unmount failed, may need force"
    echo -e "${GREEN}Unmounted${NC}"
else
    echo "Not mounted"
fi
echo ""

# Step 2: Remove fstab entry
echo "Step 2: Removing fstab entry..."
if ssh $VM_SSH "grep -q '$MAPPING_ID' /etc/fstab 2>/dev/null"; then
    ssh $VM_SSH "sudo sed -i '/$MAPPING_ID/d' /etc/fstab"
    echo -e "${GREEN}fstab entry removed${NC}"
else
    echo "No fstab entry found"
fi
echo ""

# Step 3: Remove virtiofs from VM
echo "Step 3: Removing virtiofs device from VM..."
CURRENT_CONFIG=$(ssh root@$HOST "qm config $VMID" 2>/dev/null)
if echo "$CURRENT_CONFIG" | grep -q "virtiofs0"; then
    echo "Stopping VM..."
    ssh root@$HOST "qm stop $VMID --timeout 60" || true
    sleep 5

    echo "Removing virtiofs0..."
    ssh root@$HOST "qm set $VMID --delete virtiofs0"
    echo -e "${GREEN}virtiofs0 removed${NC}"

    echo "Starting VM..."
    ssh root@$HOST "qm start $VMID"
    echo "Waiting for VM to boot (45s)..."
    sleep 45

    echo "Waiting for K3s node..."
    MAX_WAIT=180
    WAITED=0
    while [ $WAITED -lt $MAX_WAIT ]; do
        NODE_STATUS=$(KUBECONFIG="$KUBECONFIG" kubectl get nodes --no-headers 2>/dev/null | grep "k3s-vm-pumped-piglet-gpu" | awk '{print $2}')
        if [ "$NODE_STATUS" = "Ready" ]; then
            echo -e "${GREEN}Node is Ready${NC}"
            break
        fi
        sleep 10
        WAITED=$((WAITED + 10))
    done
else
    echo "No virtiofs0 configured"
fi
echo ""

# Step 4: Delete directory mapping
echo "Step 4: Deleting directory mapping..."
if ssh root@$HOST "pvesh get /cluster/mapping/dir/$MAPPING_ID" >/dev/null 2>&1; then
    ssh root@$HOST "pvesh delete /cluster/mapping/dir/$MAPPING_ID"
    echo -e "${GREEN}Mapping deleted${NC}"
else
    echo "No mapping found"
fi
echo ""

# Step 5: Optionally delete dataset
echo "Step 5: Delete ZFS dataset?"
echo ""
echo -e "${YELLOW}The dataset contains the copied recordings (~120GB)${NC}"
ssh root@$HOST "zfs list $DATASET" 2>/dev/null || echo "Dataset not found"
echo ""
read -p "Delete dataset $DATASET? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    ssh root@$HOST "zfs destroy $DATASET"
    echo -e "${GREEN}Dataset deleted${NC}"
else
    echo "Dataset kept"
fi
echo ""

echo "========================================="
echo -e "${GREEN}Rollback complete${NC}"
echo "========================================="
echo ""
echo "K3s cluster status:"
KUBECONFIG="$KUBECONFIG" kubectl get nodes -o wide
