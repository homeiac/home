#!/bin/bash
# Frigate Coral LXC - Attach Hookscript
# GitHub Issue: #168
# Attaches the hookscript to the LXC container config

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.env"

echo "=== Frigate Coral LXC - Attach Hookscript ==="
echo "Target host: $PVE_HOST_NAME ($PVE_HOST)"
echo ""

if [[ -z "$VMID" ]]; then
    echo "❌ ERROR: VMID not set in config.env"
    exit 1
fi

LXC_CONF="/etc/pve/lxc/$VMID.conf"
HOOKSCRIPT_LINE="hookscript: local:snippets/coral-lxc-hook-$VMID.sh"

echo "Container VMID: $VMID"
echo "LXC Config: $LXC_CONF"
echo ""

echo "1. Checking for existing hookscript..."
EXISTING=$(ssh root@"$PVE_HOST" "grep '^hookscript:' $LXC_CONF 2>/dev/null || echo 'NOT_FOUND'")

if [[ "$EXISTING" != "NOT_FOUND" ]]; then
    echo "   ⚠️  Hookscript already configured:"
    echo "   $EXISTING"
    echo ""
    read -p "   Replace existing hookscript? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "   Removing existing hookscript line..."
        ssh root@"$PVE_HOST" "sed -i '/^hookscript:/d' $LXC_CONF"
    else
        echo "   Skipping - no changes made"
        exit 0
    fi
fi

echo ""
echo "2. Adding hookscript line..."
ssh root@"$PVE_HOST" "echo '$HOOKSCRIPT_LINE' >> $LXC_CONF"
echo "   ✅ Added: $HOOKSCRIPT_LINE"

echo ""
echo "3. Verifying configuration..."
ssh root@"$PVE_HOST" "grep 'hookscript' $LXC_CONF"

echo ""
echo "=== Hookscript Attached ==="
echo ""
echo "NEXT: Run 30-start-container.sh to start with hookscript"
