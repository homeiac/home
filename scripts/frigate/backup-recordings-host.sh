#!/bin/bash
# Backup Frigate recordings to 3TB ZFS via kubectl from Proxmox host
# Runs on pumped-piglet - no NFS/mount required
# Deploy to: /root/scripts/backup-frigate-recordings.sh
# Cron: 0 4 * * * /root/scripts/backup-frigate-recordings.sh >> /var/log/frigate-recordings-backup.log 2>&1
#
# This script uses kubectl to tar recordings from the Frigate pod and extract to local backup.
# It's the host-based alternative to the K8s CronJob approach.
#
# NOTE: This runs OUTSIDE K8s, directly on the Proxmox host.
# For the GitOps K8s CronJob approach, see: gitops/clusters/homelab/apps/frigate/backup-recordings-cronjob.yaml

set -e

BACKUP_DIR="/local-3TB-backup/frigate-recordings"
RETENTION_DAYS=7
DATE=$(date +%Y%m%d)

# K3s kubectl config (inside VM 105)
K3S_VM="105"
KUBECTL_CMD="qm guest exec $K3S_VM -- /var/lib/rancher/k3s/bin/kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml"

echo "$(date): Starting Frigate recordings backup..."
mkdir -p "$BACKUP_DIR"

# Get Frigate pod name
POD=$($KUBECTL_CMD get pod -n frigate -l app=frigate -o jsonpath='{.items[0].metadata.name}' 2>/dev/null | tr -d '\r\n')

if [ -z "$POD" ]; then
    echo "ERROR: No Frigate pod found"
    exit 1
fi

echo "Found Frigate pod: $POD"

# Get current recording size
SIZE=$($KUBECTL_CMD exec -n frigate "$POD" -- du -sh /media/frigate/recordings 2>/dev/null | awk '{print $1}' | tr -d '\r\n')
echo "Current recordings size: $SIZE"

# Create tarball of recordings inside the pod
echo "Creating tarball in pod..."
$KUBECTL_CMD exec -n frigate "$POD" -- tar czf /tmp/recordings-backup.tar.gz -C /media/frigate recordings 2>/dev/null

# Copy tarball from pod to host via VM
# This is a multi-step process: pod -> VM filesystem -> host
TEMP_FILE="/tmp/frigate-recordings-${DATE}.tar.gz"

echo "Copying tarball from pod to VM..."
# First copy to VM's /tmp
$KUBECTL_CMD cp "frigate/${POD}:/tmp/recordings-backup.tar.gz" /tmp/recordings-backup.tar.gz 2>/dev/null || {
    echo "kubectl cp failed, trying alternative method..."
    # Alternative: cat from pod to VM file
    $KUBECTL_CMD exec -n frigate "$POD" -- cat /tmp/recordings-backup.tar.gz > /tmp/recordings-backup.tar.gz
}

# Copy from VM to host
echo "Copying tarball from VM to host..."
qm guest cmd $K3S_VM catfile /tmp/recordings-backup.tar.gz > "$TEMP_FILE" 2>/dev/null || {
    # Alternative: use scp if guest agent doesn't support catfile
    echo "catfile failed, using direct extraction approach..."

    # Instead, let's do incremental rsync-style backup
    # This is more robust for large recordings

    # Get list of camera directories
    CAMERAS=$($KUBECTL_CMD exec -n frigate "$POD" -- ls /media/frigate/recordings 2>/dev/null | tr -d '\r')

    for CAMERA in $CAMERAS; do
        echo "Backing up camera: $CAMERA"
        CAMERA_DIR="${BACKUP_DIR}/${CAMERA}"
        mkdir -p "$CAMERA_DIR"

        # Get list of date directories for this camera
        DATES=$($KUBECTL_CMD exec -n frigate "$POD" -- ls /media/frigate/recordings/"$CAMERA" 2>/dev/null | tr -d '\r' | tail -${RETENTION_DAYS})

        for DATE_DIR in $DATES; do
            echo "  Processing: $CAMERA/$DATE_DIR"
            TARGET_DIR="${CAMERA_DIR}/${DATE_DIR}"
            mkdir -p "$TARGET_DIR"

            # Get list of hour directories
            HOURS=$($KUBECTL_CMD exec -n frigate "$POD" -- ls /media/frigate/recordings/"$CAMERA"/"$DATE_DIR" 2>/dev/null | tr -d '\r')

            for HOUR in $HOURS; do
                HOUR_DIR="${TARGET_DIR}/${HOUR}"
                mkdir -p "$HOUR_DIR"

                # Copy all .mp4 files in this hour directory
                # Using tar for efficiency
                $KUBECTL_CMD exec -n frigate "$POD" -- tar cf - -C /media/frigate/recordings/"$CAMERA"/"$DATE_DIR"/"$HOUR" . 2>/dev/null | tar xf - -C "$HOUR_DIR" 2>/dev/null || true
            done
        done
    done

    rm -f "$TEMP_FILE"
    TEMP_FILE=""
}

# If tarball method worked, extract it
if [ -n "$TEMP_FILE" ] && [ -f "$TEMP_FILE" ]; then
    echo "Extracting tarball to backup directory..."
    tar xzf "$TEMP_FILE" -C "$BACKUP_DIR"
    rm -f "$TEMP_FILE"
fi

# Cleanup recordings in pod's /tmp
$KUBECTL_CMD exec -n frigate "$POD" -- rm -f /tmp/recordings-backup.tar.gz 2>/dev/null || true

# Cleanup old backups (keep last 7 days)
echo "Cleaning up recordings older than ${RETENTION_DAYS} days..."
find "$BACKUP_DIR" -type f -mtime +${RETENTION_DAYS} -delete 2>/dev/null || true
find "$BACKUP_DIR" -type d -empty -delete 2>/dev/null || true

# Report
BACKUP_SIZE=$(du -sh "$BACKUP_DIR" 2>/dev/null | awk '{print $1}')
echo "$(date): Backup complete"
echo "Backup location: $BACKUP_DIR"
echo "Backup size: $BACKUP_SIZE"
echo ""
echo "Backup contents:"
ls -la "$BACKUP_DIR" 2>/dev/null || echo "No backups found"
