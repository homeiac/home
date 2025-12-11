#!/bin/bash
# Frigate Coral LXC - Add USB Passthrough
# GitHub Issue: #168
# Adds dev0 line for Coral USB to LXC config

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.env"

echo "=== Frigate Coral LXC - Add USB Passthrough ==="
echo "Target host: $PVE_HOST_NAME ($PVE_HOST)"
echo ""

if [[ -z "$VMID" ]]; then
    echo "❌ ERROR: VMID not set in config.env"
    exit 1
fi

LXC_CONF="/etc/pve/lxc/$VMID.conf"
DEV_PATH="/dev/bus/usb/$CORAL_BUS/$CORAL_DEV"
DEV_LINE="dev0: $DEV_PATH,mode=0666"

echo "Container VMID: $VMID"
echo "LXC Config: $LXC_CONF"
echo "Device Path: $DEV_PATH"
echo ""

echo "1. Checking if dev0 already exists..."
EXISTING=$(ssh root@"$PVE_HOST" "grep '^dev0:' $LXC_CONF 2>/dev/null || echo 'NOT_FOUND'")

if [[ "$EXISTING" != "NOT_FOUND" ]]; then
    echo "   ⚠️  dev0 already exists:"
    echo "   $EXISTING"
    echo ""
    read -p "   Replace existing dev0? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "   Removing existing dev0..."
        ssh root@"$PVE_HOST" "sed -i '/^dev0:/d' $LXC_CONF"
    else
        echo "   Skipping - no changes made"
        exit 0
    fi
fi

echo ""
echo "2. Adding USB passthrough line..."
ssh root@"$PVE_HOST" "echo '$DEV_LINE' >> $LXC_CONF"
echo "   ✅ Added: $DEV_LINE"

echo ""
echo "3. Verifying configuration..."
ssh root@"$PVE_HOST" "grep '^dev0:' $LXC_CONF"

echo ""
echo "=== USB Passthrough Added ==="
echo ""
echo "NEXT: Run 12-add-cgroup-permissions.sh"
