#!/bin/bash
# 04-check-coral-in-vm.sh - Verify Coral USB is visible inside VM 105

set -e

HOST="pumped-piglet.maas"
VMID=105

echo "========================================="
echo "Step 4: Check Coral USB in VM $VMID"
echo "========================================="
echo ""

echo "Checking USB devices in VM via qm guest exec..."
ssh root@$HOST "qm guest exec $VMID -- lsusb" 2>&1 | grep -iE "google|1a6e|18d1" || {
  echo "No Coral found via qm guest exec, trying direct SSH..."
  ssh ubuntu@k3s-vm-pumped-piglet-gpu "lsusb" 2>/dev/null | grep -iE "google|1a6e|18d1" || {
    echo "ERROR: Coral USB not visible in VM!"
    echo "Check USB passthrough config and try replugging Coral."
    exit 1
  }
}
echo ""

echo "Checking /dev/bus/usb..."
ssh ubuntu@k3s-vm-pumped-piglet-gpu "ls -la /dev/bus/usb/*/" 2>/dev/null | head -20 || echo "Could not list USB devices"
echo ""

echo "========================================="
echo "Coral visible in VM. Next: Run 05-install-libedgetpu.sh"
echo "========================================="
