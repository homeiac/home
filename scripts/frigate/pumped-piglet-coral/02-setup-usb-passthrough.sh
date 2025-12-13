#!/bin/bash
# 02-setup-usb-passthrough.sh - Configure USB passthrough for Coral on VM 105
#
# Adds both bootloader (1a6e:089a) and initialized (18d1:9302) USB IDs

set -e

HOST="pumped-piglet.maas"
VMID=105

echo "========================================="
echo "Step 2: Setup USB Passthrough for VM $VMID"
echo "========================================="
echo ""

# Check current config
echo "Current USB config:"
ssh root@$HOST "qm config $VMID | grep -E '^usb' || echo 'No USB passthrough configured'"
echo ""

# Add USB passthrough for both Coral states
echo "Adding USB passthrough for Coral (bootloader + initialized)..."
ssh root@$HOST "qm set $VMID --usb0 host=1a6e:089a,usb3=1 2>/dev/null || echo 'usb0 already set'"
ssh root@$HOST "qm set $VMID --usb1 host=18d1:9302,usb3=1 2>/dev/null || echo 'usb1 already set'"
echo ""

# Verify config
echo "Updated USB config:"
ssh root@$HOST "qm config $VMID | grep -E '^usb'"
echo ""

echo "========================================="
echo "USB passthrough configured."
echo "Next: Run 03-restart-vm.sh to apply changes"
echo "========================================="
