#!/bin/bash
# 09-cleanup-still-fawn.sh - Remove Coral USB passthrough from still-fawn VM 108
#
# Now that Coral is working on pumped-piglet, we can clean up still-fawn

set -e

HOST="still-fawn.maas"
VMID=108

echo "========================================="
echo "Cleanup: Remove Coral from still-fawn"
echo "========================================="
echo ""

# Check current USB config
echo "Current USB config on VM $VMID:"
ssh root@$HOST "qm config $VMID | grep -E '^usb' || echo 'No USB passthrough configured'"
echo ""

read -p "Remove Coral USB passthrough from still-fawn? (y/N) " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
  echo "Aborted."
  exit 0
fi

# Remove USB passthrough (if configured)
echo "Removing USB passthrough..."
ssh root@$HOST "qm set $VMID --delete usb0 2>/dev/null || echo 'usb0 not configured'"
ssh root@$HOST "qm set $VMID --delete usb1 2>/dev/null || echo 'usb1 not configured'"
echo ""

# Verify removal
echo "Updated USB config:"
ssh root@$HOST "qm config $VMID | grep -E '^usb' || echo 'No USB passthrough configured'"
echo ""

echo "========================================="
echo "still-fawn cleanup complete."
echo "Coral USB is now exclusively on pumped-piglet."
echo "========================================="
