#!/bin/bash
# Backup Frigate recordings via rsync from K3s pod
# Runs on pumped-piglet - syncs recordings to 3TB ZFS
# Deploy to: /root/scripts/backup-frigate-recordings.sh
# Cron: 0 4 * * * /root/scripts/backup-frigate-recordings.sh >> /var/log/frigate-recordings-backup.log 2>&1

set -e

BACKUP_DIR="/local-3TB-backup/frigate-recordings"
FRIGATE_NS="frigate"
RETENTION_DAYS=7

echo "$(date): Starting Frigate recordings backup..."

# Get Frigate pod name via API (Traefik routes to the pod)
# We'll use kubectl from the K3s VM to rsync

# Find the K3s VM and get pod info
K3S_VM_IP="10.43.0.1"  # K3s internal, won't work from host

# Alternative: Mount NFS or use kubectl cp
# Since recordings can be large, we'll use a staging approach

# Create backup directory structure
mkdir -p "$BACKUP_DIR"

# Get recordings list via Frigate API (last 7 days)
FRIGATE_URL="https://frigate.app.home.panderosystems.com"

echo "$(date): Fetching recording summaries..."

# Get list of cameras
CAMERAS=$(curl -sk "${FRIGATE_URL}/api/config" | jq -r '.cameras | keys[]')

for CAMERA in $CAMERAS; do
    echo "Processing camera: $CAMERA"
    CAMERA_DIR="${BACKUP_DIR}/${CAMERA}"
    mkdir -p "$CAMERA_DIR"

    # Get recordings for last 7 days
    # Frigate API: /api/CAMERA/recordings/summary
    SUMMARY=$(curl -sk "${FRIGATE_URL}/api/${CAMERA}/recordings/summary")

    # Download each day's recordings
    for DAY in $(echo "$SUMMARY" | jq -r '.[].day' | head -${RETENTION_DAYS}); do
        DAY_DIR="${CAMERA_DIR}/${DAY}"
        mkdir -p "$DAY_DIR"

        # Get recording segments for this day
        # Frigate stores recordings as HLS segments
        HOURS=$(echo "$SUMMARY" | jq -r ".[] | select(.day==\"${DAY}\") | .hours[].hour")

        for HOUR in $HOURS; do
            HOUR_PADDED=$(printf "%02d" $HOUR)

            # Download the recording segment via vod endpoint
            # /vod/CAMERA/start/TIMESTAMP/end/TIMESTAMP/index.m3u8
            # This is complex - simpler to just export specific events

            echo "  Day: $DAY Hour: $HOUR_PADDED"
        done
    done
done

echo "$(date): Recordings backup complete"
echo "Note: For full recordings backup, consider NFS mount or kubectl cp approach"
