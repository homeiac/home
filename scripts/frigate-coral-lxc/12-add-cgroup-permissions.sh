#!/bin/bash
# Frigate Coral LXC - Add Cgroup Permissions
# GitHub Issue: #168
# Adds USB cgroup permissions to LXC config

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.env"

echo "=== Frigate Coral LXC - Add Cgroup Permissions ==="
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

echo "1. Checking existing cgroup settings..."
EXISTING_CGROUP=$(ssh root@"$PVE_HOST" "grep 'lxc.cgroup2.devices.allow: c 189' $LXC_CONF 2>/dev/null || echo 'NOT_FOUND'")
EXISTING_AUTODEV=$(ssh root@"$PVE_HOST" "grep 'lxc.autodev' $LXC_CONF 2>/dev/null || echo 'NOT_FOUND'")

if [[ "$EXISTING_CGROUP" != "NOT_FOUND" ]]; then
    echo "   ✅ USB cgroup already configured"
else
    echo "   Adding USB cgroup permission..."
    ssh root@"$PVE_HOST" "echo 'lxc.cgroup2.devices.allow: c 189:* rwm' >> $LXC_CONF"
    echo "   ✅ Added: lxc.cgroup2.devices.allow: c 189:* rwm"
fi

if [[ "$EXISTING_AUTODEV" != "NOT_FOUND" ]]; then
    echo "   ✅ autodev already configured"
else
    echo "   Adding autodev setting..."
    ssh root@"$PVE_HOST" "echo 'lxc.autodev: 1' >> $LXC_CONF"
    echo "   ✅ Added: lxc.autodev: 1"
fi

echo ""
echo "2. Verifying configuration..."
echo "   Cgroup settings:"
ssh root@"$PVE_HOST" "grep 'lxc.cgroup2' $LXC_CONF || echo '   (none)'"
echo ""
echo "   Autodev setting:"
ssh root@"$PVE_HOST" "grep 'lxc.autodev' $LXC_CONF || echo '   (none)'"

echo ""
echo "=== Cgroup Permissions Added ==="
echo ""
echo "NEXT: Run 13-add-vaapi-passthrough.sh (optional) or 20-create-hookscript.sh"
