#!/bin/bash
# Frigate Coral LXC - Full Rollback
# GitHub Issue: #168
# Destroys container and cleans up all created resources

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.env"

echo "=== Frigate Coral LXC - FULL ROLLBACK ==="
echo "Target host: $PVE_HOST_NAME ($PVE_HOST)"
echo ""
echo "⚠️  WARNING: This will destroy the container and remove all related files!"
echo ""

if [[ -z "$VMID" ]]; then
    echo "❌ ERROR: VMID not set in config.env"
    echo "   Cannot proceed without VMID"
    exit 1
fi

echo "Container VMID: $VMID"
echo ""

read -p "Are you sure you want to proceed? Type 'YES' to confirm: " -r
echo
if [[ "$REPLY" != "YES" ]]; then
    echo "Rollback cancelled."
    exit 0
fi

echo ""
echo "1. Stopping container..."
ssh root@"$PVE_HOST" "pct stop $VMID 2>/dev/null" || echo "   Container may already be stopped"
sleep 3

echo ""
echo "2. Destroying container..."
ssh root@"$PVE_HOST" "pct destroy $VMID 2>/dev/null" || echo "   Container may not exist"

echo ""
echo "3. Removing hookscript..."
HOOKSCRIPT_PATH="/var/lib/vz/snippets/coral-lxc-hook-$VMID.sh"
ssh root@"$PVE_HOST" "rm -f $HOOKSCRIPT_PATH" || echo "   Hookscript may not exist"
echo "   Removed $HOOKSCRIPT_PATH"

echo ""
echo "4. Checking for udev rules to remove..."
read -p "   Remove /etc/udev/rules.d/98-coral.rules? [y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    ssh root@"$PVE_HOST" "rm -f /etc/udev/rules.d/98-coral.rules"
    ssh root@"$PVE_HOST" "udevadm control --reload-rules"
    echo "   ✅ Udev rules removed"
else
    echo "   Keeping udev rules"
fi

echo ""
echo "=== FULL ROLLBACK COMPLETE ==="
echo ""
echo "Removed:"
echo "  - Container $VMID"
echo "  - Hookscript $HOOKSCRIPT_PATH"
echo "  - Udev rules (if confirmed)"
echo ""
echo "Remember to update config.env to clear VMID if re-deploying."
