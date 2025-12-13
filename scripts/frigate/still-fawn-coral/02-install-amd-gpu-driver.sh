#!/bin/bash
# 02-install-amd-gpu-driver.sh - Install AMD GPU drivers in K3s VM 108
#
# Installs kernel modules and VAAPI drivers for AMD GPU hardware acceleration

set -e

HOST="still-fawn.maas"
VMID=108

echo "========================================="
echo "Phase 2: Install AMD GPU Driver in VM $VMID"
echo "========================================="
echo ""

# Step 1: Install kernel modules extra
echo "Step 1: Installing linux-modules-extra..."
ssh root@$HOST "qm guest exec $VMID -- bash -c 'apt update && apt install -y linux-modules-extra-\$(uname -r)'" 2>&1 | grep -E 'out-data|err-data' || true
echo ""

# Step 2: Load amdgpu module
echo "Step 2: Loading amdgpu kernel module..."
ssh root@$HOST "qm guest exec $VMID -- modprobe amdgpu" 2>&1
sleep 2
echo ""

# Step 3: Verify /dev/dri exists
echo "Step 3: Verifying /dev/dri..."
ssh root@$HOST "qm guest exec $VMID -- ls -la /dev/dri/" 2>&1
echo ""

# Step 4: Install VAAPI drivers
echo "Step 4: Installing VAAPI drivers..."
ssh root@$HOST "qm guest exec $VMID -- bash -c 'apt install -y mesa-va-drivers vainfo'" 2>&1 | grep -E 'out-data|err-data' || true
echo ""

# Step 5: Test VAAPI
echo "Step 5: Testing VAAPI..."
ssh root@$HOST "qm guest exec $VMID -- bash -c 'vainfo --display drm --device /dev/dri/renderD128 2>&1 | head -20'" 2>&1
echo ""

# Step 6: Make amdgpu load at boot
echo "Step 6: Adding amdgpu to /etc/modules..."
ssh root@$HOST "qm guest exec $VMID -- bash -c 'grep -q amdgpu /etc/modules || echo amdgpu >> /etc/modules'" 2>&1
echo ""

echo "========================================="
echo "AMD GPU driver installation complete!"
echo "========================================="
echo ""
echo "Expected: /dev/dri/card0 and /dev/dri/renderD128"
echo "VAAPI should show AMD Radeon profiles"
