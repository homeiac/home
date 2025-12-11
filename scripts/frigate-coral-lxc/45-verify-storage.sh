#!/bin/bash
# Frigate Coral LXC - Verify Storage Mount
# GitHub Issue: #168
#
# Verifies storage is properly mounted and writable for Frigate recordings.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.env"

CONTAINER_MOUNT_PATH="/media/frigate"

echo "=== Frigate Coral LXC - Verify Storage ==="
echo "Target host: $PVE_HOST_NAME ($PVE_HOST)"
echo "Container: $VMID"
echo ""

# Check container is running
echo "1. Checking container status..."
STATUS=$(ssh root@"$PVE_HOST" "pct status $VMID" 2>/dev/null | awk '{print $2}')
if [ "$STATUS" != "running" ]; then
    echo "   ❌ Container $VMID is not running"
    exit 1
fi
echo "   ✅ Container is running"

# Check LXC config for mount
echo ""
echo "2. Checking LXC config for mount points..."
MOUNT_CONFIG=$(ssh root@"$PVE_HOST" "grep -E '^mp[0-9]:' /etc/pve/lxc/$VMID.conf" 2>/dev/null || echo "NONE")
if [ "$MOUNT_CONFIG" = "NONE" ]; then
    echo "   ❌ No mount points configured in LXC config"
    echo "   Run ./44-add-storage-mount.sh first"
    exit 1
fi
echo "   Mount points configured:"
echo "$MOUNT_CONFIG" | while read line; do
    echo "   - $line"
done

# Check mount inside container
echo ""
echo "3. Checking storage mount inside container..."
STORAGE_DF=$(ssh root@"$PVE_HOST" "pct exec $VMID -- df -h $CONTAINER_MOUNT_PATH 2>/dev/null" || echo "FAILED")

if echo "$STORAGE_DF" | grep -q "$CONTAINER_MOUNT_PATH"; then
    echo "   ✅ Storage mounted:"
    echo "$STORAGE_DF" | tail -1 | awk '{print "      Size: "$2", Used: "$3", Available: "$4", Use%: "$5}'
else
    echo "   ❌ Storage not mounted at $CONTAINER_MOUNT_PATH"
    echo "   Available mounts:"
    ssh root@"$PVE_HOST" "pct exec $VMID -- df -h" 2>/dev/null | head -10
    exit 1
fi

# Check if writable
echo ""
echo "4. Testing write access..."
TEST_FILE="$CONTAINER_MOUNT_PATH/.frigate-write-test-$$"
if ssh root@"$PVE_HOST" "pct exec $VMID -- touch $TEST_FILE" 2>/dev/null; then
    ssh root@"$PVE_HOST" "pct exec $VMID -- rm -f $TEST_FILE" 2>/dev/null || true
    echo "   ✅ Storage is writable"
else
    echo "   ❌ Storage is NOT writable"
    echo "   Check permissions on host mount"
    exit 1
fi

# Check Frigate directories
echo ""
echo "5. Checking Frigate storage directories..."
FRIGATE_DIRS="recordings clips snapshots"
for dir in $FRIGATE_DIRS; do
    DIR_PATH="$CONTAINER_MOUNT_PATH/$dir"
    if ssh root@"$PVE_HOST" "pct exec $VMID -- test -d $DIR_PATH" 2>/dev/null; then
        DIR_SIZE=$(ssh root@"$PVE_HOST" "pct exec $VMID -- du -sh $DIR_PATH 2>/dev/null" | awk '{print $1}')
        echo "   ✅ $dir: $DIR_SIZE"
    else
        echo "   ⚠️  $dir: not created yet (will be created when Frigate runs)"
    fi
done

# Check available space
echo ""
echo "6. Storage capacity check..."
AVAIL_GB=$(ssh root@"$PVE_HOST" "pct exec $VMID -- df -BG $CONTAINER_MOUNT_PATH 2>/dev/null" | tail -1 | awk '{print $4}' | tr -d 'G')
if [ -n "$AVAIL_GB" ] && [ "$AVAIL_GB" -gt 100 ]; then
    echo "   ✅ Sufficient space: ${AVAIL_GB}GB available"
elif [ -n "$AVAIL_GB" ]; then
    echo "   ⚠️  Low space warning: ${AVAIL_GB}GB available"
    echo "   Frigate may fill storage quickly with multiple cameras"
fi

echo ""
echo "=== Storage Verification Complete ==="
echo ""
echo "Storage path: $CONTAINER_MOUNT_PATH"
echo "Status: Ready for Frigate recordings"
