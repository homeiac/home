#!/bin/bash
# Backup HAOS dashboard config
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="$SCRIPT_DIR/../../proxmox/backups/haos-dashboards"

HA_VM_ID="116"
HA_HOST="chief-horse.maas"
DASHBOARD="${1:-lovelace.dashboard_frigate}"

mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/${DASHBOARD}.backup.${TIMESTAMP}.json"

echo "=== Backing up HAOS Dashboard ==="
echo "Dashboard: $DASHBOARD"
echo ""

ssh -o StrictHostKeyChecking=no "root@$HA_HOST" \
    "qm guest exec $HA_VM_ID -- cat /mnt/data/supervisor/homeassistant/.storage/$DASHBOARD" 2>/dev/null | \
    jq -r '.["out-data"]' > "$BACKUP_FILE"

if [[ -s "$BACKUP_FILE" ]]; then
    echo "✅ Backup saved: $BACKUP_FILE"
    ls -la "$BACKUP_FILE"
else
    echo "❌ Backup failed - file is empty"
    rm -f "$BACKUP_FILE"
    exit 1
fi
