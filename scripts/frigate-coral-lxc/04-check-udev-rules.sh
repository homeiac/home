#!/bin/bash
# Frigate Coral LXC - Check Udev Rules
# GitHub Issue: #168
# Verifies if Coral udev rules exist

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.env"

echo "=== Frigate Coral LXC - Check Udev Rules ==="
echo "Target host: $PVE_HOST_NAME ($PVE_HOST)"
echo ""

echo "1. Checking for Coral udev rules..."
RULES_EXIST=$(ssh root@"$PVE_HOST" "ls /etc/udev/rules.d/*coral* 2>/dev/null || echo 'NO_RULES'")

if [[ "$RULES_EXIST" == "NO_RULES" ]]; then
    echo "   ⚠️  No Coral-specific udev rules found"
    NEED_RULES=true
else
    echo "   ✅ Found udev rules:"
    echo "   $RULES_EXIST"
    NEED_RULES=false
fi

echo ""
echo "2. Checking current device permissions..."
DEV_PATH="/dev/bus/usb/$CORAL_BUS/$CORAL_DEV"
PERMS=$(ssh root@"$PVE_HOST" "stat -c '%a' $DEV_PATH 2>/dev/null || echo 'UNKNOWN'")

if [[ "$PERMS" == "666" ]]; then
    echo "   ✅ Permissions are 0666 (world read/write)"
    NEED_RULES=false
elif [[ "$PERMS" == "UNKNOWN" ]]; then
    echo "   ❌ Could not check permissions for $DEV_PATH"
else
    echo "   ⚠️  Permissions are 0$PERMS (should be 0666)"
    NEED_RULES=true
fi

echo ""
echo "   Full device info:"
ssh root@"$PVE_HOST" "ls -la $DEV_PATH 2>/dev/null || echo '   Device not found'"

echo ""
echo "=== Udev Rules Check Complete ==="
echo ""
if [[ "$NEED_RULES" == "true" ]]; then
    echo "ACTION REQUIRED: Run 05-create-udev-rules.sh to create rules"
else
    echo "NO ACTION NEEDED: Udev rules or permissions are already correct"
fi
