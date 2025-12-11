#!/bin/bash
# Frigate Coral LXC - Add VAAPI Passthrough (Optional)
# GitHub Issue: #168
# Adds GPU/VAAPI passthrough for hardware video decoding

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.env"

echo "=== Frigate Coral LXC - Add VAAPI Passthrough ==="
echo "Target host: $PVE_HOST_NAME ($PVE_HOST)"
echo ""

if [[ -z "$VMID" ]]; then
    echo "❌ ERROR: VMID not set in config.env"
    exit 1
fi

LXC_CONF="/etc/pve/lxc/$VMID.conf"

echo "Container VMID: $VMID"
echo "LXC Config: $LXC_CONF"
echo ""

echo "1. Checking for GPU on host..."
GPU_INFO=$(ssh root@"$PVE_HOST" "ls -la /dev/dri/ 2>/dev/null || echo 'NO_DRI'")

if [[ "$GPU_INFO" == "NO_DRI" ]]; then
    echo "   ⚠️  No /dev/dri found on host"
    echo "   VAAPI passthrough may not be possible"
    exit 0
fi

echo "   GPU devices found:"
echo "$GPU_INFO" | sed 's/^/   /'

echo ""
echo "2. Adding GPU cgroup permissions..."
ssh root@"$PVE_HOST" "grep -q 'lxc.cgroup2.devices.allow: c 226:0' $LXC_CONF 2>/dev/null || echo 'lxc.cgroup2.devices.allow: c 226:0 rwm' >> $LXC_CONF"
ssh root@"$PVE_HOST" "grep -q 'lxc.cgroup2.devices.allow: c 226:128' $LXC_CONF 2>/dev/null || echo 'lxc.cgroup2.devices.allow: c 226:128 rwm' >> $LXC_CONF"
echo "   ✅ Added GPU cgroup permissions"

echo ""
echo "3. Adding renderD128 mount entry..."
MOUNT_LINE="lxc.mount.entry: /dev/dri/renderD128 dev/dri/renderD128 none bind,optional,create=file"
ssh root@"$PVE_HOST" "grep -q 'renderD128' $LXC_CONF 2>/dev/null || echo '$MOUNT_LINE' >> $LXC_CONF"
echo "   ✅ Added renderD128 mount"

echo ""
echo "4. Verifying configuration..."
ssh root@"$PVE_HOST" "grep -E '(226|renderD128)' $LXC_CONF"

echo ""
echo "=== VAAPI Passthrough Added ==="
echo ""
echo "NEXT: Run 20-create-hookscript.sh"
