#!/bin/bash
# Frigate Coral LXC - Configure Cameras
# GitHub Issue: #168
#
# Applies camera configuration to Frigate from backup or template.
# This is the CRITICAL step - Frigate is useless without cameras.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.env"

BACKUP_DIR="/Users/10381054/code/home/proxmox/backups"
HOST_BACKUP_DIR="$BACKUP_DIR/$PVE_HOST_NAME"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

# Camera config source - use existing backup from fun-bedbug
CAMERA_CONFIG_SOURCE="$BACKUP_DIR/frigate-app-config.yml"

echo "=== Frigate Coral LXC - Configure Cameras ==="
echo "Target host: $PVE_HOST_NAME ($PVE_HOST)"
echo "Container: $VMID"
echo ""

# Check container is running
echo "1. Checking container status..."
STATUS=$(ssh root@"$PVE_HOST" "pct status $VMID" 2>/dev/null | awk '{print $2}')
if [ "$STATUS" != "running" ]; then
    echo "   ❌ Container $VMID is not running (status: $STATUS)"
    exit 1
fi
echo "   ✅ Container is running"

# Check camera config source exists
echo ""
echo "2. Checking camera config source..."
if [ ! -f "$CAMERA_CONFIG_SOURCE" ]; then
    echo "   ❌ Camera config not found: $CAMERA_CONFIG_SOURCE"
    echo ""
    echo "   Please provide camera configuration:"
    echo "   - Copy from existing Frigate instance"
    echo "   - Create from template: $SCRIPT_DIR/camera-config-template.yml"
    exit 1
fi
echo "   ✅ Found: $CAMERA_CONFIG_SOURCE"

# Show cameras that will be configured
echo ""
echo "3. Cameras to configure:"
grep "^  [a-z]" "$CAMERA_CONFIG_SOURCE" | grep -v "^  #" | head -10
CAMERA_COUNT=$(grep -E "^  [a-z_]+:" "$CAMERA_CONFIG_SOURCE" | grep -v "enabled\|host\|port\|user\|password\|streams" | wc -l | tr -d ' ')
echo "   Total cameras: $CAMERA_COUNT"

# Backup current config
echo ""
echo "4. Backing up current Frigate config..."
mkdir -p "$HOST_BACKUP_DIR"
CURRENT_BACKUP="$HOST_BACKUP_DIR/frigate-config-before-cameras-$TIMESTAMP.yml"
ssh root@"$PVE_HOST" "pct exec $VMID -- cat /config/config.yml" > "$CURRENT_BACKUP"
echo "   ✅ Backed up to: $CURRENT_BACKUP"

# Apply camera config
echo ""
echo "5. Applying camera configuration..."
cat "$CAMERA_CONFIG_SOURCE" | ssh root@"$PVE_HOST" "pct exec $VMID -- tee /config/config.yml > /dev/null"
echo "   ✅ Camera config applied"

# Verify config was applied
echo ""
echo "6. Verifying config..."
APPLIED_CAMERAS=$(ssh root@"$PVE_HOST" "pct exec $VMID -- grep -E '^  [a-z_]+:' /config/config.yml" 2>/dev/null | grep -v "enabled\|host\|port\|user\|password\|streams" | wc -l | tr -d ' ')
if [ "$APPLIED_CAMERAS" -gt 0 ]; then
    echo "   ✅ Config applied with $APPLIED_CAMERAS camera entries"
else
    echo "   ❌ Config verification failed"
    echo "   Restoring backup..."
    cat "$CURRENT_BACKUP" | ssh root@"$PVE_HOST" "pct exec $VMID -- tee /config/config.yml > /dev/null"
    exit 1
fi

echo ""
echo "=== Camera Configuration Complete ==="
echo ""
echo "Cameras configured: $CAMERA_COUNT"
echo "Backup saved to: $CURRENT_BACKUP"
echo ""
echo "NEXT STEPS:"
echo "1. Run ./41-restart-frigate.sh to apply changes"
echo "2. Run ./43-verify-cameras.sh to verify cameras are working"
echo "3. Access Frigate UI to see camera feeds"
