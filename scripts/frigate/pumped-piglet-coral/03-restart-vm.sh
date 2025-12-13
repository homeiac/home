#!/bin/bash
# 03-restart-vm.sh - Restart VM 105 to apply USB passthrough changes
#
# WARNING: This will briefly take down the K3s node

set -e

HOST="pumped-piglet.maas"
VMID=105

echo "========================================="
echo "Step 3: Restart VM $VMID"
echo "========================================="
echo ""

echo "WARNING: This will restart VM $VMID (k3s-vm-pumped-piglet-gpu)"
echo "The K3s node will be briefly unavailable."
echo ""
read -p "Press Enter to continue or Ctrl+C to abort..."

echo "Stopping VM $VMID..."
ssh root@$HOST "qm stop $VMID"
echo "Waiting 5 seconds..."
sleep 5

echo "Starting VM $VMID..."
ssh root@$HOST "qm start $VMID"
echo ""

echo "Waiting for VM to boot (60 seconds)..."
for i in {1..12}; do
  echo -n "."
  sleep 5
done
echo ""

echo "Checking VM status..."
ssh root@$HOST "qm status $VMID"
echo ""

echo "========================================="
echo "VM restarted. Next: Run 04-check-coral-in-vm.sh"
echo "========================================="
