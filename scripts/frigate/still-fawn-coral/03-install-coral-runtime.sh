#!/bin/bash
# 03-install-coral-runtime.sh - Install Coral TPU runtime in K3s VM 108
#
# Installs libedgetpu for Google Coral USB TPU support

set -e

HOST="still-fawn.maas"
VMID=108

echo "========================================="
echo "Phase 3: Install Coral Runtime in VM $VMID"
echo "========================================="
echo ""

# Step 1: Add Coral repository
echo "Step 1: Adding Coral Edge TPU repository..."
ssh root@$HOST "qm guest exec $VMID -- bash -c 'echo \"deb https://packages.cloud.google.com/apt coral-edgetpu-stable main\" | tee /etc/apt/sources.list.d/coral-edgetpu.list'"
echo ""

# Step 2: Add Google signing key
echo "Step 2: Adding Google signing key..."
ssh root@$HOST "qm guest exec $VMID -- bash -c 'curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg | gpg --dearmor -o /usr/share/keyrings/coral-edgetpu-archive-keyring.gpg'"
ssh root@$HOST "qm guest exec $VMID -- bash -c 'echo \"deb [signed-by=/usr/share/keyrings/coral-edgetpu-archive-keyring.gpg] https://packages.cloud.google.com/apt coral-edgetpu-stable main\" | tee /etc/apt/sources.list.d/coral-edgetpu.list'"
echo ""

# Step 3: Update and install libedgetpu
echo "Step 3: Installing libedgetpu1-std..."
ssh root@$HOST "qm guest exec $VMID -- bash -c 'apt update && apt install -y libedgetpu1-std'" 2>&1 | grep -E 'out-data|err-data' || true
echo ""

# Step 4: Verify Coral USB is visible
echo "Step 4: Verifying Coral USB device..."
ssh root@$HOST "qm guest exec $VMID -- lsusb" 2>&1 | grep -i google || echo "No Google USB device found"
echo ""

# Step 5: Check device permissions
echo "Step 5: Checking /dev/bus/usb permissions..."
ssh root@$HOST "qm guest exec $VMID -- bash -c 'ls -la /dev/bus/usb/*/'" 2>&1
echo ""

echo "========================================="
echo "Coral runtime installation complete!"
echo "========================================="
echo ""
echo "Coral USB TPU should now be usable by Frigate"
