#!/bin/bash
# 04a-check-dev-dri.sh - CRITICAL check for /dev/dri on host
#
# The PVE Helper Script frigate-install.sh ALWAYS runs:
#   chgrp video /dev/dri
# for privileged containers (CTTYPE=0).
#
# This is NOT controlled by var_gpu option - it's unconditional.
# If /dev/dri doesn't exist, the install fails with exit code 39.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.env"

echo "=== Frigate Coral LXC - Check /dev/dri (CRITICAL) ==="
echo "Target host: $PVE_HOST_NAME ($PVE_HOST)"
echo ""

# Check if /dev/dri exists
echo "1. Checking for /dev/dri..."
DRI_EXISTS=$(ssh root@${PVE_HOST} "ls -la /dev/dri/ 2>/dev/null && echo 'EXISTS' || echo 'MISSING'")

if echo "$DRI_EXISTS" | grep -q "EXISTS"; then
    echo "   ✅ /dev/dri exists:"
    ssh root@${PVE_HOST} "ls -la /dev/dri/"
    echo ""
    echo "=== /dev/dri Check PASSED ==="
    exit 0
fi

# /dev/dri is missing - investigate why
echo "   ❌ /dev/dri does NOT exist"
echo ""
echo "2. Checking for GPU hardware..."
ssh root@${PVE_HOST} "lspci | grep -i vga" || echo "   No VGA devices found"
echo ""

echo "3. Checking for GPU driver blacklist..."
BLACKLIST=$(ssh root@${PVE_HOST} "grep -rh 'blacklist.*amdgpu\|blacklist.*radeon\|blacklist.*i915\|blacklist.*nouveau' /etc/modprobe.d/ 2>/dev/null || echo 'none'")
if [ "$BLACKLIST" != "none" ]; then
    echo "   ⚠️  GPU DRIVERS ARE BLACKLISTED:"
    echo "$BLACKLIST"
    echo ""
    echo "   Files containing blacklist:"
    ssh root@${PVE_HOST} "grep -rl 'blacklist.*amdgpu\|blacklist.*radeon\|blacklist.*i915\|blacklist.*nouveau' /etc/modprobe.d/ 2>/dev/null || true"
else
    echo "   No GPU driver blacklist found"
fi
echo ""

echo "4. Checking loaded GPU modules..."
ssh root@${PVE_HOST} "lsmod | grep -E 'amdgpu|radeon|i915|nouveau' || echo '   No GPU modules loaded'"
echo ""

echo "=== /dev/dri Check FAILED ==="
echo ""
echo "╔════════════════════════════════════════════════════════════════════╗"
echo "║  BLOCKING ERROR: PVE Helper Script install will fail without       ║"
echo "║  /dev/dri. The frigate-install.sh script unconditionally runs      ║"
echo "║  'chgrp video /dev/dri' for privileged containers.                 ║"
echo "╠════════════════════════════════════════════════════════════════════╣"
echo "║  FIX OPTIONS:                                                      ║"
echo "║                                                                    ║"
echo "║  Option A: Enable GPU driver (requires reboot)                     ║"
echo "║    1. Remove blacklist entries from /etc/modprobe.d/*.conf         ║"
echo "║    2. Run: update-initramfs -u                                     ║"
echo "║    3. Reboot host                                                  ║"
echo "║                                                                    ║"
echo "║  Option B: Create dummy /dev/dri (workaround, no real GPU)         ║"
echo "║    ssh root@${PVE_HOST} 'mkdir -p /dev/dri'                        ║"
echo "║    Note: VAAPI won't work, but Coral TPU will                      ║"
echo "╚════════════════════════════════════════════════════════════════════╝"
echo ""
exit 1
