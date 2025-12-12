#!/bin/bash
#
# 12-restore-db-from-pbs.sh
#
# Restore frigate.db from PBS backup of LXC 113 and copy to K8s Frigate
#
# The old LXC 113 backups contain the full frigate database with reviewsegment
# entries, thumbnails, and event data that we need for the Review UI.
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"
NAMESPACE="frigate"
HOST="pumped-piglet.maas"

# Use Dec 6 backup - 159GB, should have most complete data before migration
BACKUP_ID="homelab-backup:backup/ct/113/2025-12-06T06:35:41Z"
TEMP_VMID="9113"  # Temporary VMID for restore

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo "========================================="
echo "Restore Frigate DB from PBS Backup"
echo "========================================="
echo ""
echo "Backup: $BACKUP_ID"
echo "Host: $HOST"
echo ""

# Step 1: Restore LXC to temporary ID (won't start it)
echo "Step 1: Restoring LXC 113 backup to temporary container $TEMP_VMID..."
ssh root@$HOST << REMOTE_STEP1
set -e

# Check if temp container exists and remove it
if pct status $TEMP_VMID >/dev/null 2>&1; then
    echo "  Removing existing temp container $TEMP_VMID..."
    pct destroy $TEMP_VMID --force 2>/dev/null || true
fi

# Restore the backup to temp container (unprivileged, won't start)
echo "  Restoring backup (this may take a few minutes)..."
pct restore $TEMP_VMID "$BACKUP_ID" \
    --storage local-2TB-zfs \
    --unprivileged 1 \
    --ignore-unpack-errors 1 \
    --start 0

echo "  Restore complete"
REMOTE_STEP1

echo ""
echo "Step 2: Extracting frigate.db from restored container..."
ssh root@$HOST << REMOTE_STEP2
set -e

# Find the rootfs mount point
ROOTFS=\$(pct config $TEMP_VMID | grep "^rootfs:" | sed 's/.*://' | cut -d',' -f1)
echo "  Container rootfs: \$ROOTFS"

# Get the actual path
MOUNT_PATH="/var/lib/lxc/$TEMP_VMID/rootfs"
if [ ! -d "\$MOUNT_PATH" ]; then
    # Try ZFS mount
    MOUNT_PATH=\$(zfs list -H -o mountpoint local-2TB-zfs/subvol-$TEMP_VMID-disk-0 2>/dev/null || echo "")
fi

echo "  Mount path: \$MOUNT_PATH"

# Find frigate.db
echo "  Searching for frigate.db..."
find "\$MOUNT_PATH" -name "frigate.db" -type f 2>/dev/null | head -5

# Copy to temp location
DB_PATH=\$(find "\$MOUNT_PATH" -name "frigate.db" -type f 2>/dev/null | head -1)
if [ -n "\$DB_PATH" ]; then
    echo "  Found: \$DB_PATH"
    cp "\$DB_PATH" /tmp/frigate-old.db
    ls -la /tmp/frigate-old.db

    # Check contents
    echo ""
    echo "  Database contents:"
    sqlite3 /tmp/frigate-old.db "SELECT 'recordings:', COUNT(*) FROM recordings"
    sqlite3 /tmp/frigate-old.db "SELECT 'reviewsegment:', COUNT(*) FROM reviewsegment"
    sqlite3 /tmp/frigate-old.db "SELECT 'event:', COUNT(*) FROM event"
else
    echo "  ERROR: frigate.db not found!"
    exit 1
fi
REMOTE_STEP2

echo ""
echo "Step 3: Copying old database to local machine..."
scp root@$HOST:/tmp/frigate-old.db /tmp/frigate-old.db
ls -la /tmp/frigate-old.db

echo ""
echo "Step 4: Checking old database contents..."
sqlite3 /tmp/frigate-old.db << 'SQL'
.headers on
SELECT 'Recordings' as table_name, COUNT(*) as count FROM recordings
UNION ALL
SELECT 'ReviewSegments', COUNT(*) FROM reviewsegment
UNION ALL
SELECT 'Events', COUNT(*) FROM event
UNION ALL
SELECT 'Timeline', COUNT(*) FROM timeline;
SQL

echo ""
echo "Step 5: Cleanup - removing temporary container..."
ssh root@$HOST "pct destroy $TEMP_VMID --force 2>/dev/null || true"

echo ""
echo "========================================="
echo -e "${GREEN}Old database extracted to /tmp/frigate-old.db${NC}"
echo "========================================="
echo ""
echo "Next: Run 13-merge-databases.sh to merge into K8s Frigate"
