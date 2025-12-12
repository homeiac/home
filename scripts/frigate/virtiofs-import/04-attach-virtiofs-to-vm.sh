#!/bin/bash
#
# 04-attach-virtiofs-to-vm.sh
#
# Attach virtiofs device to K3s VM
# Requires VM restart - will wait for K3s node to rejoin cluster
#

set -euo pipefail

HOST="pumped-piglet.maas"
VMID="105"
MAPPING_ID="frigate-import"
KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "========================================="
echo "Attach VirtioFS to VM $VMID"
echo "========================================="
echo ""
echo "Host: $HOST"
echo "VMID: $VMID"
echo "Mapping: $MAPPING_ID"
echo ""

# Pre-flight: Check K3s cluster health
echo "Step 1: Pre-flight - checking K3s cluster..."
KUBECONFIG="$KUBECONFIG" kubectl get nodes -o wide
echo ""

NODE_COUNT=$(KUBECONFIG="$KUBECONFIG" kubectl get nodes --no-headers | wc -l | tr -d ' ')
if [ "$NODE_COUNT" -lt 3 ]; then
    echo -e "${YELLOW}Warning: Only $NODE_COUNT nodes ready. Expected 3.${NC}"
fi
echo ""

# Check if virtiofs already attached
echo "Step 2: Checking current VM config..."
CURRENT_CONFIG=$(ssh root@$HOST "qm config $VMID")
echo "$CURRENT_CONFIG" | grep -E "virtiofs|name:|memory:|cores:" || true
echo ""

if echo "$CURRENT_CONFIG" | grep -q "virtiofs0"; then
    echo -e "${YELLOW}virtiofs0 already configured${NC}"
    echo ""
    echo "Current virtiofs config:"
    echo "$CURRENT_CONFIG" | grep virtiofs
    echo ""
    echo "To remove: ssh root@$HOST 'qm set $VMID --delete virtiofs0'"
    exit 0
fi

# Check mapping exists
echo "Step 3: Verifying directory mapping exists..."
if ! ssh root@$HOST "pvesh get /cluster/mapping/dir/$MAPPING_ID" >/dev/null 2>&1; then
    echo -e "${RED}Directory mapping '$MAPPING_ID' not found!${NC}"
    echo "Run 03-create-directory-mapping.sh first"
    exit 1
fi
echo -e "${GREEN}Mapping exists${NC}"
echo ""

# Stop VM
echo "Step 4: Stopping VM $VMID..."
echo -e "${YELLOW}This will cause K3s node downtime${NC}"
STOP_START=$(date +%s)

ssh root@$HOST "qm stop $VMID --timeout 60"
echo -e "${GREEN}VM stopped${NC}"
echo ""

# Add virtiofs
echo "Step 5: Adding virtiofs device..."
ssh root@$HOST "qm set $VMID --virtiofs0 $MAPPING_ID"
echo -e "${GREEN}virtiofs0 added${NC}"
echo ""

# Verify config
echo "Step 6: Verifying VM config..."
ssh root@$HOST "qm config $VMID" | grep virtiofs
echo ""

# Start VM
echo "Step 7: Starting VM $VMID..."
ssh root@$HOST "qm start $VMID"
echo -e "${GREEN}VM started${NC}"
echo ""

# Wait for VM to boot
echo "Step 8: Waiting for VM to boot (45s)..."
sleep 45
echo ""

# Wait for K3s node to rejoin
echo "Step 9: Waiting for K3s node to rejoin cluster..."
MAX_WAIT=180
WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
    NODE_STATUS=$(KUBECONFIG="$KUBECONFIG" kubectl get nodes --no-headers 2>/dev/null | grep "k3s-vm-pumped-piglet-gpu" | awk '{print $2}')
    if [ "$NODE_STATUS" = "Ready" ]; then
        echo -e "${GREEN}Node is Ready!${NC}"
        break
    fi
    echo "  Node status: $NODE_STATUS (waiting...)"
    sleep 10
    WAITED=$((WAITED + 10))
done

if [ $WAITED -ge $MAX_WAIT ]; then
    echo -e "${RED}Timeout waiting for node to become Ready${NC}"
    echo "Check manually: kubectl get nodes"
    exit 1
fi

STOP_END=$(date +%s)
DOWNTIME=$((STOP_END - STOP_START))

echo ""
echo "========================================="
echo -e "${GREEN}VirtioFS attached successfully!${NC}"
echo "========================================="
echo ""
echo "VM downtime: ${DOWNTIME} seconds"
echo ""

# Final cluster check
echo "Final K3s cluster status:"
KUBECONFIG="$KUBECONFIG" kubectl get nodes -o wide
echo ""

echo "Next: Run 05-mount-in-vm.sh"
