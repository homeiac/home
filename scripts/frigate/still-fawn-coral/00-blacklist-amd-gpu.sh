#!/bin/bash
# 00-blacklist-amd-gpu.sh - Blacklist AMD GPU for VFIO passthrough
#
# This script prepares the AMD GPU on still-fawn for passthrough to a VM
# by binding it to vfio-pci instead of the amdgpu driver.
#
# REQUIRES REBOOT after running!
#
# GPU: AMD Radeon RX 470/480/570/580 (1002:67df + 1002:aaf0)

set -e

HOST="still-fawn.maas"

echo "========================================="
echo "Phase 0: Blacklist AMD GPU for VFIO"
echo "========================================="
echo ""

# Step 1: Check current GPU binding
echo "Step 1: Current GPU driver binding..."
ssh root@$HOST "lspci -nnk -s 01:00" 2>/dev/null
echo ""

# Step 2: Check existing blacklist/vfio configs
echo "Step 2: Checking existing modprobe configs..."
ssh root@$HOST "cat /etc/modprobe.d/blacklist.conf 2>/dev/null || echo 'No blacklist.conf'"
echo "---"
ssh root@$HOST "cat /etc/modprobe.d/vfio*.conf 2>/dev/null || echo 'No vfio configs'"
echo ""

# Step 3: Create vfio-pci config for AMD GPU
echo "Step 3: Creating vfio-pci config for AMD GPU..."
ssh root@$HOST "cat > /etc/modprobe.d/vfio-amd.conf << 'EOF'
# AMD Radeon RX 470/480/570/580 for VFIO passthrough
options vfio-pci ids=1002:67df,1002:aaf0 disable_vga=1
EOF"
echo "  Created /etc/modprobe.d/vfio-amd.conf"

# Step 4: Blacklist amdgpu driver
echo "Step 4: Blacklisting amdgpu driver..."
ssh root@$HOST "grep -q 'blacklist amdgpu' /etc/modprobe.d/blacklist.conf 2>/dev/null || echo 'blacklist amdgpu' >> /etc/modprobe.d/blacklist.conf"
ssh root@$HOST "grep -q 'blacklist snd_hda_intel' /etc/modprobe.d/blacklist.conf 2>/dev/null || echo 'blacklist snd_hda_intel' >> /etc/modprobe.d/blacklist.conf"
echo "  Added blacklist entries"

# Step 5: Add vfio modules to initramfs
echo "Step 5: Ensuring vfio modules load early..."
ssh root@$HOST "grep -q 'vfio' /etc/modules 2>/dev/null || cat >> /etc/modules << 'EOF'
vfio
vfio_iommu_type1
vfio_pci
EOF"
echo "  Added vfio modules to /etc/modules"

# Step 6: Update initramfs
echo "Step 6: Updating initramfs..."
ssh root@$HOST "update-initramfs -u -k all" 2>/dev/null
echo "  Initramfs updated"
echo ""

# Step 7: Show what was configured
echo "Step 7: Final configuration..."
echo "=== /etc/modprobe.d/vfio-amd.conf ==="
ssh root@$HOST "cat /etc/modprobe.d/vfio-amd.conf"
echo ""
echo "=== Blacklist entries ==="
ssh root@$HOST "grep -E 'amdgpu|snd_hda' /etc/modprobe.d/blacklist.conf"
echo ""

echo "========================================="
echo "AMD GPU blacklist configured!"
echo "========================================="
echo ""
echo "NEXT STEP: Reboot still-fawn to apply changes"
echo ""
echo "Run: ssh root@still-fawn.maas 'reboot'"
echo ""
echo "After reboot, verify with:"
echo "  ssh root@still-fawn.maas 'lspci -nnk -s 01:00'"
echo "  Expected: Kernel driver in use: vfio-pci"
