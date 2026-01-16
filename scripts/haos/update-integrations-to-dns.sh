#!/bin/bash
# Update HA integrations from IP addresses to DNS hostnames
# Update Home Assistant integrations from IP addresses to DNS hostnames
# Prevents issues when MetalLB IP assignments change
#

set -eo pipefail

# Configuration
HA_PROXMOX_HOST="chief-horse.maas"
HA_VMID="116"
CONFIG_PATH="/mnt/data/supervisor/homeassistant/.storage/core.config_entries"

echo "========================================="
echo "Update HA Integrations to DNS"
echo "========================================="
echo ""

# IP to DNS mappings (space-separated pairs: "old|new")
MAPPINGS=(
    "http://192.168.4.81|http://ollama.app.homelab"
    "http://192.168.4.82:5000|http://frigate.app.homelab"
    "http://192.168.4.83:5000|http://frigate.app.homelab"
    "http://192.168.4.85:5000|http://frigate.app.homelab"
    "192.168.4.82:5000/|frigate.app.homelab"
    "192.168.4.83:5000/|frigate.app.homelab"
    "192.168.4.85:5000/|frigate.app.homelab"
)

# Step 1: Show current integrations with IPs
echo "Step 1: Current integrations with IP addresses..."
CURRENT=$(ssh root@$HA_PROXMOX_HOST "qm guest exec $HA_VMID -- cat $CONFIG_PATH" 2>/dev/null | jq -r '."out-data"')
echo "$CURRENT" | jq '[.data.entries[] | select(.data.url) | {domain, url: .data.url}]'
echo ""

# Step 2: Create backup
echo "Step 2: Creating backup..."
BACKUP_PATH="${CONFIG_PATH}.backup.$(date +%Y%m%d_%H%M%S)"
ssh root@$HA_PROXMOX_HOST "qm guest exec $HA_VMID -- cp $CONFIG_PATH $BACKUP_PATH"
echo "Backup created: $BACKUP_PATH"
echo ""

# Step 3: Apply mappings
echo "Step 3: Applying DNS mappings..."
for MAPPING in "${MAPPINGS[@]}"; do
    IP="${MAPPING%%|*}"
    DNS="${MAPPING##*|}"
    echo "  Replacing: $IP -> $DNS"
    ssh root@$HA_PROXMOX_HOST "qm guest exec $HA_VMID -- sed -i 's|$IP|$DNS|g' $CONFIG_PATH" 2>/dev/null || true
done
echo ""

# Step 4: Verify changes
echo "Step 4: Verifying changes..."
UPDATED=$(ssh root@$HA_PROXMOX_HOST "qm guest exec $HA_VMID -- cat $CONFIG_PATH" 2>/dev/null | jq -r '."out-data"')
echo "$UPDATED" | jq '[.data.entries[] | select(.data.url) | {domain, url: .data.url}]'
echo ""

# Check if any IPs remain
REMAINING_IPS=$(echo "$UPDATED" | grep -oE "192\.168\.[0-9]+\.[0-9]+" | sort -u || true)
if [[ -n "$REMAINING_IPS" ]]; then
    echo "WARNING: Some IPs still present (may be intentional):"
    echo "$REMAINING_IPS"
    echo ""
fi

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
echo "Backup location: $BACKUP_PATH"
echo ""
echo "To rollback:"
echo "  ssh root@$HA_PROXMOX_HOST 'qm guest exec $HA_VMID -- cp $BACKUP_PATH $CONFIG_PATH'"
echo "  ssh root@$HA_PROXMOX_HOST 'qm guest exec $HA_VMID -- ha core restart'"
