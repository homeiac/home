#!/bin/bash
#
# update-ha-frigate-url.sh
#
# Update Home Assistant Frigate integration URL via QEMU guest agent
# Uses the method documented in blog-frigate-server-migration.md
#

set -euo pipefail

# Configuration
HA_PROXMOX_HOST="chief-horse.maas"
HA_VMID="116"
CONFIG_PATH="/mnt/data/supervisor/homeassistant/.storage/core.config_entries"

# Default URLs
OLD_URL="${1:-http://192.168.4.80}"
NEW_URL="${2:-http://192.168.4.83:5000}"

echo "========================================="
echo "Update Home Assistant Frigate URL"
echo "========================================="
echo ""
echo "Proxmox Host: $HA_PROXMOX_HOST"
echo "HA VM ID: $HA_VMID"
echo ""
echo "Old URL: $OLD_URL"
echo "New URL: $NEW_URL"
echo ""

# Step 1: Show current config
echo "Step 1: Current Frigate config..."
CURRENT=$(ssh root@$HA_PROXMOX_HOST "qm guest exec $HA_VMID -- cat $CONFIG_PATH" 2>/dev/null | jq -r '."out-data"' | jq '.data.entries[] | select(.domain == "frigate") | .data')
echo "$CURRENT"
echo ""

CURRENT_URL=$(echo "$CURRENT" | jq -r '.url')
if [[ "$CURRENT_URL" != "$OLD_URL" ]]; then
    echo "WARNING: Current URL ($CURRENT_URL) doesn't match expected old URL ($OLD_URL)"
    echo "Updating sed pattern to match current URL..."
    OLD_URL="$CURRENT_URL"
fi

# Step 2: Backup
echo "Step 2: Creating backup..."
BACKUP_PATH="${CONFIG_PATH}.backup.$(date +%Y%m%d_%H%M%S)"
ssh root@$HA_PROXMOX_HOST "qm guest exec $HA_VMID -- cp $CONFIG_PATH $BACKUP_PATH"
echo "Backup created: $BACKUP_PATH"
echo ""

# Step 3: Update URL
echo "Step 3: Updating URL from $OLD_URL to $NEW_URL..."
ssh root@$HA_PROXMOX_HOST "qm guest exec $HA_VMID -- sed -i 's|$OLD_URL|$NEW_URL|g' $CONFIG_PATH"
echo "URL updated."
echo ""

# Step 4: Verify
echo "Step 4: Verifying change..."
NEW_CONFIG_URL=$(ssh root@$HA_PROXMOX_HOST "qm guest exec $HA_VMID -- cat $CONFIG_PATH" 2>/dev/null | jq -r '."out-data"' | jq -r '.data.entries[] | select(.domain == "frigate") | .data.url')
echo "New URL in config: $NEW_CONFIG_URL"

if [[ "$NEW_CONFIG_URL" == "$NEW_URL" ]]; then
    echo "URL updated successfully!"
else
    echo "ERROR: URL update failed!"
    exit 1
fi
echo ""

# Step 5: Restart HA
echo "Step 5: Restarting Home Assistant..."
timeout 10 ssh root@$HA_PROXMOX_HOST "qm guest exec $HA_VMID -- ha core restart" 2>&1 || echo "(Expected timeout - HA is restarting)"
echo ""

# Step 6: Wait for HA
echo "Step 6: Waiting for Home Assistant to restart..."
for i in {1..24}; do
    sleep 5
    if curl -s --max-time 3 http://homeassistant.maas:8123/ 2>/dev/null | head -c 50 | grep -q "Home Assistant"; then
        echo "Home Assistant is back up!"
        break
    fi
    echo "  Waiting... ($i/24)"
done
echo ""

echo "========================================="
echo "Migration complete!"
echo "========================================="
echo ""
echo "New Frigate URL: $NEW_URL"
echo "Backup location: $BACKUP_PATH"
echo ""
echo "To rollback:"
echo "  ssh root@$HA_PROXMOX_HOST 'qm guest exec $HA_VMID -- cp $BACKUP_PATH $CONFIG_PATH'"
echo "  ssh root@$HA_PROXMOX_HOST 'qm guest exec $HA_VMID -- ha core restart'"
