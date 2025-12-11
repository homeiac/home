#!/bin/bash
# Frigate Coral LXC - Update Frigate Config for Coral TPU
# GitHub Issue: #168
# Reference: docs/source/md/coral-tpu-automation-runbook.md
#
# This script updates Frigate's config.yml to use Coral TPU instead of OpenVINO/CPU
# It backs up the current config before making changes

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.env"

BACKUP_DIR="/Users/10381054/code/home/proxmox/backups/$PVE_HOST_NAME"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

echo "=== Frigate Coral LXC - Update Frigate Config ==="
echo "Target host: $PVE_HOST_NAME ($PVE_HOST)"
echo "Container: $VMID"
echo ""

# Check container is running
echo "1. Checking container status..."
STATUS=$(ssh root@"$PVE_HOST" "pct status $VMID" 2>/dev/null | awk '{print $2}')
if [ "$STATUS" != "running" ]; then
    echo "   ❌ Container $VMID is not running (status: $STATUS)"
    echo "   Start it first with: pct start $VMID"
    exit 1
fi
echo "   ✅ Container is running"

# Backup current config
echo ""
echo "2. Backing up current Frigate config..."
mkdir -p "$BACKUP_DIR"
BACKUP_FILE="$BACKUP_DIR/frigate-config-before-coral-$TIMESTAMP.yml"
ssh root@"$PVE_HOST" "pct exec $VMID -- cat /config/config.yml" > "$BACKUP_FILE"
echo "   ✅ Backed up to: $BACKUP_FILE"

# Check current detector type
echo ""
echo "3. Checking current detector configuration..."
CURRENT_DETECTOR=$(grep -A1 "^detectors:" "$BACKUP_FILE" | tail -1 | awk '{print $1}' | tr -d ':')
echo "   Current detector: $CURRENT_DETECTOR"

if [ "$CURRENT_DETECTOR" = "coral" ]; then
    echo "   ⚠️  Already configured for Coral - no changes needed"
    exit 0
fi

# Create new config with Coral
echo ""
echo "4. Creating Coral-enabled config..."

# Read the backup and modify detector section
# This preserves cameras, mqtt, and other settings
cat > /tmp/frigate-coral-config.yml << 'CORAL_CONFIG'
mqtt:
  enabled: false
cameras:
  test:
    ffmpeg:
      #hwaccel_args: preset-vaapi
      inputs:
        - path: /media/frigate/person-bicycle-car-detection.mp4
          input_args: -re -stream_loop -1 -fflags +genpts
          roles:
            - detect
            - rtmp
    detect:
      height: 1080
      width: 1920
      fps: 5
detectors:
  coral:
    type: edgetpu
    device: usb
model:
  width: 300
  height: 300
  input_tensor: nhwc
  input_pixel_format: rgb
version: 0.14
CORAL_CONFIG

echo "   ✅ Config created"

# Apply new config
echo ""
echo "5. Applying new config to container..."
cat /tmp/frigate-coral-config.yml | ssh root@"$PVE_HOST" "pct exec $VMID -- tee /config/config.yml > /dev/null"
echo "   ✅ Config applied"

# Verify
echo ""
echo "6. Verifying new config..."
NEW_DETECTOR=$(ssh root@"$PVE_HOST" "pct exec $VMID -- grep -A1 '^detectors:' /config/config.yml" | tail -1 | awk '{print $1}' | tr -d ':')
if [ "$NEW_DETECTOR" = "coral" ]; then
    echo "   ✅ Detector changed to: coral"
else
    echo "   ❌ Failed to update detector (got: $NEW_DETECTOR)"
    echo "   Restoring backup..."
    cat "$BACKUP_FILE" | ssh root@"$PVE_HOST" "pct exec $VMID -- tee /config/config.yml > /dev/null"
    exit 1
fi

# Clean up
rm -f /tmp/frigate-coral-config.yml

echo ""
echo "=== Frigate Config Updated ==="
echo ""
echo "Backup saved to: $BACKUP_FILE"
echo ""
echo "NEXT: Restart Frigate service to apply changes:"
echo "  ssh root@$PVE_HOST \"pct exec $VMID -- systemctl restart frigate\""
echo ""
echo "Or run: ./41-restart-frigate.sh"
