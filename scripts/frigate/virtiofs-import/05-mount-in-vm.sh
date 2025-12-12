#!/bin/bash
#
# 05-mount-in-vm.sh
#
# Mount virtiofs filesystem inside K3s VM and persist via fstab
# Uses qm guest exec via qemu-guest-agent
#

set -euo pipefail

HOST="pumped-piglet.maas"
VMID="105"
MOUNT_TAG="frigate-import"
MOUNT_POINT="/mnt/frigate-import"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Helper function to run commands in VM via qm guest exec
vm_exec() {
    ssh root@$HOST "qm guest exec $VMID -- $1"
}

echo "========================================="
echo "Mount VirtioFS in VM"
echo "========================================="
echo ""
echo "Host: $HOST"
echo "VMID: $VMID"
echo "Mount tag: $MOUNT_TAG"
echo "Mount point: $MOUNT_POINT"
echo ""

# Check guest agent is responding
echo "Step 1: Checking guest agent..."
if ! ssh root@$HOST "qm agent $VMID ping" 2>/dev/null; then
    echo -e "${RED}Guest agent not responding${NC}"
    echo "Run 00-install-guest-agent.sh first"
    exit 1
fi
echo -e "${GREEN}Guest agent responding${NC}"
echo ""

# Check if already mounted
echo "Step 2: Checking if already mounted..."
RESULT=$(vm_exec "mountpoint -q $MOUNT_POINT && echo MOUNTED || echo NOTMOUNTED" 2>/dev/null)
if echo "$RESULT" | grep -q "MOUNTED"; then
    echo -e "${YELLOW}$MOUNT_POINT is already mounted${NC}"
    echo ""
    vm_exec "df -h $MOUNT_POINT"
    echo ""
    vm_exec "ls -la $MOUNT_POINT"
    exit 0
fi
echo "Not mounted yet"
echo ""

# Create mount point
echo "Step 3: Creating mount point..."
vm_exec "mkdir -p $MOUNT_POINT"
echo -e "${GREEN}Mount point created${NC}"
echo ""

# Mount virtiofs
echo "Step 4: Mounting virtiofs..."
vm_exec "mount -t virtiofs $MOUNT_TAG $MOUNT_POINT"
echo -e "${GREEN}Mounted${NC}"
echo ""

# Check if fstab entry exists and add if not
echo "Step 5: Adding to fstab for persistence..."
FSTAB_CHECK=$(vm_exec "grep $MOUNT_TAG /etc/fstab || echo NOTFOUND" 2>/dev/null)
if echo "$FSTAB_CHECK" | grep -q "NOTFOUND"; then
    vm_exec "bash -c 'echo \"$MOUNT_TAG $MOUNT_POINT virtiofs defaults,nofail 0 0\" >> /etc/fstab'"
    echo -e "${GREEN}Added to fstab${NC}"
else
    echo -e "${YELLOW}fstab entry already exists${NC}"
fi
echo ""

# Verify mount
echo "Step 6: Verifying mount..."
vm_exec "df -h $MOUNT_POINT"
echo ""
vm_exec "ls -la $MOUNT_POINT"
echo ""

# Check Frigate data structure
echo "Step 7: Checking Frigate data structure..."
FRIGATE_CHECK=$(vm_exec "test -d $MOUNT_POINT/frigate && echo EXISTS || echo NOTFOUND" 2>/dev/null)
if echo "$FRIGATE_CHECK" | grep -q "EXISTS"; then
    echo -e "${GREEN}Found frigate directory${NC}"
    vm_exec "ls -la $MOUNT_POINT/frigate"
    echo ""
    vm_exec "du -sh $MOUNT_POINT/frigate/*"
else
    echo -e "${YELLOW}Checking root level contents${NC}"
    vm_exec "ls -la $MOUNT_POINT"
fi
echo ""

echo "========================================="
echo -e "${GREEN}VirtioFS mounted successfully!${NC}"
echo "========================================="
echo ""
echo "Mount point: $MOUNT_POINT"
echo "Frigate data: $MOUNT_POINT/frigate/"
echo "Persistent: Yes (via fstab)"
echo ""
echo "Next: Run 06-verify-frigate-access.sh"
