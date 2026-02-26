#!/bin/bash
# Backup Frigate recordings to 3TB ZFS via rsync
# Runs on pumped-piglet - requires NFS mount from K3s VM
# Deploy to: /root/scripts/backup-frigate-recordings.sh
# Cron: 0 4 * * * /root/scripts/backup-frigate-recordings.sh >> /var/log/frigate-recordings-backup.log 2>&1
#
# SETUP (one-time):
#   1. On K3s VM (105): Install NFS server, export /var/lib/rancher/k3s/storage
#   2. On pumped-piglet: mount k3s-vm-ip:/var/lib/rancher/k3s/storage /mnt/k3s-storage
#   3. Find Frigate PVC path: ls /mnt/k3s-storage/pvc-*/recordings/
#
# ALTERNATIVE: Use this script which works without NFS setup

set -e

BACKUP_DIR="/local-3TB-backup/frigate-recordings"
FRIGATE_URL="https://frigate.app.home.panderosystems.com"
RETENTION_DAYS=7
DATE=$(date +%Y%m%d)

echo "$(date): Starting Frigate recordings backup..."
mkdir -p "$BACKUP_DIR"

# Method: Export recordings via Frigate API
# Frigate 0.14+ has /api/export endpoint for creating video exports

# Get list of cameras
CAMERAS=$(curl -sk "${FRIGATE_URL}/api/config" | jq -r '.cameras | keys[]')

TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

for CAMERA in $CAMERAS; do
    echo "Processing camera: $CAMERA"
    mkdir -p "${TEMP_DIR}/${CAMERA}"

    # Get recordings summary
    SUMMARY=$(curl -sk "${FRIGATE_URL}/api/${CAMERA}/recordings/summary")

    # Get available days
    DAYS=$(echo "$SUMMARY" | jq -r '.[].day' | head -${RETENTION_DAYS})

    for DAY in $DAYS; do
        echo "  Downloading recordings for $DAY..."

        # Get time range for this day
        START_TS=$(date -d "${DAY} 00:00:00" +%s 2>/dev/null || date -j -f "%Y-%m-%d %H:%M:%S" "${DAY} 00:00:00" +%s)
        END_TS=$(date -d "${DAY} 23:59:59" +%s 2>/dev/null || date -j -f "%Y-%m-%d %H:%M:%S" "${DAY} 23:59:59" +%s)

        # Download via VOD endpoint (m3u8 -> mp4 would need ffmpeg)
        # Simpler: use the recordings endpoint to get segment list
        SEGMENTS=$(curl -sk "${FRIGATE_URL}/api/${CAMERA}/recordings?after=${START_TS}&before=${END_TS}" | jq -r '.[].id')

        for SEG_ID in $SEGMENTS; do
            # Download segment
            curl -sk "${FRIGATE_URL}/api/recordings/${SEG_ID}/clip.mp4" \
                -o "${TEMP_DIR}/${CAMERA}/${DAY}-${SEG_ID}.mp4" 2>/dev/null || true
        done
    done
done

# Create tarball
echo "$(date): Creating backup tarball..."
tar czf "${BACKUP_DIR}/frigate-recordings-${DATE}.tar.gz" -C "$TEMP_DIR" .

# Cleanup old backups (keep 7)
ls -t "${BACKUP_DIR}"/frigate-recordings-*.tar.gz 2>/dev/null | tail -n +8 | xargs -r rm -f

SIZE=$(ls -lh "${BACKUP_DIR}/frigate-recordings-${DATE}.tar.gz" 2>/dev/null | awk '{print $5}')
echo "$(date): Backup complete: frigate-recordings-${DATE}.tar.gz ($SIZE)"
echo "Current backups:"
ls -lh "${BACKUP_DIR}"/frigate-recordings-*.tar.gz 2>/dev/null || echo "No backups found"
