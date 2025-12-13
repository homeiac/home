#!/bin/bash
#
# rollback-ha-frigate-url.sh
#
# Rollback Home Assistant Frigate URL to previous backup
#

set -euo pipefail

# Configuration
HA_PROXMOX_HOST="chief-horse.maas"
HA_VMID="116"
CONFIG_PATH="/mnt/data/supervisor/homeassistant/.storage/core.config_entries"

echo "========================================="
echo "Rollback Home Assistant Frigate URL"
echo "========================================="
echo ""

# Find the most recent backup
echo "Finding most recent backup..."
BACKUP=$(ssh root@$HA_PROXMOX_HOST "qm guest exec $HA_VMID -- ls -t ${CONFIG_PATH}.backup.* 2>/dev/null | head -1" 2>/dev/null | jq -r '."out-data"' | tr -d '\n')

if [[ -z "$BACKUP" ]] || [[ "$BACKUP" == "null" ]]; then
    echo "ERROR: No backup found!"
    echo "Looking for backups matching: ${CONFIG_PATH}.backup.*"
    exit 1
fi

echo "Found backup: $BACKUP"
echo ""

# Show current config
echo "Current Frigate URL:"
ssh root@$HA_PROXMOX_HOST "qm guest exec $HA_VMID -- cat $CONFIG_PATH" 2>/dev/null | jq -r '."out-data"' | jq -r '.data.entries[] | select(.domain == "frigate") | .data.url'
echo ""

# Show backup config
echo "Backup Frigate URL:"
ssh root@$HA_PROXMOX_HOST "qm guest exec $HA_VMID -- cat $BACKUP" 2>/dev/null | jq -r '."out-data"' | jq -r '.data.entries[] | select(.domain == "frigate") | .data.url'
echo ""

read -p "Restore from this backup? (y/n): " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Rollback cancelled."
    exit 0
fi

# Restore backup
echo "Restoring backup..."
ssh root@$HA_PROXMOX_HOST "qm guest exec $HA_VMID -- cp $BACKUP $CONFIG_PATH"
echo "Backup restored."
echo ""

# Restart HA
echo "Restarting Home Assistant..."
timeout 10 ssh root@$HA_PROXMOX_HOST "qm guest exec $HA_VMID -- ha core restart" 2>&1 || echo "(Expected timeout - HA is restarting)"
echo ""

# Wait for HA
echo "Waiting for Home Assistant to restart..."
for i in {1..24}; do
    sleep 5
    if curl -s --max-time 3 http://homeassistant.maas:8123/ 2>/dev/null | head -c 50 | grep -q "Home Assistant"; then
        echo "Home Assistant is back up!"
        break
    fi
    echo "  Waiting... ($i/24)"
done
echo ""

# Verify
echo "Verifying rollback..."
NEW_URL=$(ssh root@$HA_PROXMOX_HOST "qm guest exec $HA_VMID -- cat $CONFIG_PATH" 2>/dev/null | jq -r '."out-data"' | jq -r '.data.entries[] | select(.domain == "frigate") | .data.url')
echo "Current Frigate URL: $NEW_URL"
echo ""

echo "========================================="
echo "Rollback complete!"
echo "========================================="
