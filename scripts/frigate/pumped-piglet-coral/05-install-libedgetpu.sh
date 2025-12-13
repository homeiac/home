#!/bin/bash
# 05-install-libedgetpu.sh - Install Coral TPU runtime in VM 105
#
# Uses qm guest exec (NOT SSH - SSH doesn't work on this VM)

set -e

HOST="pumped-piglet.maas"
VMID=105

echo "========================================="
echo "Step 5: Install libedgetpu in VM $VMID"
echo "========================================="
echo ""

# Check if already installed
echo "Checking if libedgetpu is already installed..."
RESULT=$(ssh root@$HOST "qm guest exec $VMID -- bash -c 'dpkg -l 2>/dev/null | grep libedgetpu || echo NOT_INSTALLED'" 2>&1)
if echo "$RESULT" | grep -q "libedgetpu"; then
  echo "libedgetpu already installed:"
  echo "$RESULT" | grep libedgetpu
  echo ""
  echo "Skipping installation."
  exit 0
fi

echo "libedgetpu not installed. Installing..."
echo ""

# Add Coral repository
echo "Adding Coral Edge TPU repository..."
ssh root@$HOST "qm guest exec $VMID -- bash -c 'echo \"deb https://packages.cloud.google.com/apt coral-edgetpu-stable main\" | tee /etc/apt/sources.list.d/coral-edgetpu.list'"
echo ""

# Add signing key
echo "Adding Google signing key..."
ssh root@$HOST "qm guest exec $VMID -- bash -c 'curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key add -'"
echo ""

# Update and install
echo "Running apt update..."
ssh root@$HOST "qm guest exec $VMID -- apt-get update" 2>&1 | tail -5
echo ""

echo "Installing libedgetpu1-std..."
ssh root@$HOST "qm guest exec $VMID -- apt-get install -y libedgetpu1-std" 2>&1 | tail -10
echo ""

# Verify
echo "Verifying installation..."
ssh root@$HOST "qm guest exec $VMID -- dpkg -l" 2>&1 | grep libedgetpu || echo "WARNING: libedgetpu not found after install"
echo ""

echo "========================================="
echo "libedgetpu installation complete."
echo "========================================="
