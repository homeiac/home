#!/bin/bash
# Sync PostgreSQL backups from K8s PVC to Google Drive
#
# This script can be run:
# 1. Manually from a node with kubectl and rclone
# 2. As part of a K8s CronJob (see gdrive-sync-cronjob.yaml)
#
# Prerequisites:
# - rclone configured with Google Drive (run setup-rclone-gdrive.sh)
# - kubectl access to K8s cluster
# - PostgreSQL backup CronJob running (backup-cronjob.yaml)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REMOTE_NAME="${RCLONE_REMOTE:-gdrive-backup}"
BACKUP_FOLDER="${GDRIVE_FOLDER:-homelab-backup/postgres}"
LOCAL_BACKUP_DIR="${LOCAL_BACKUP_DIR:-/tmp/pg-backup-sync}"
KUBECTL="${KUBECTL:-kubectl}"
NAMESPACE="database"
PVC_NAME="postgres-backup"

echo "========================================="
echo "PostgreSQL → Google Drive Sync"
echo "========================================="
echo "Remote: $REMOTE_NAME:$BACKUP_FOLDER"
echo ""

# Check rclone
if ! command -v rclone &>/dev/null; then
    echo "ERROR: rclone not installed. Run setup-rclone-gdrive.sh first."
    exit 1
fi

# Check rclone remote
if ! rclone listremotes 2>/dev/null | grep -q "^${REMOTE_NAME}:$"; then
    echo "ERROR: rclone remote '$REMOTE_NAME' not found."
    echo "Run setup-rclone-gdrive.sh to configure Google Drive."
    exit 1
fi

# Create local temp directory
mkdir -p "$LOCAL_BACKUP_DIR"

# Find the pod that has the backup PVC mounted
echo "Finding PostgreSQL backup pod..."
BACKUP_POD=$($KUBECTL get pods -n "$NAMESPACE" -o jsonpath='{.items[*].metadata.name}' | tr ' ' '\n' | grep postgres || true)

if [ -z "$BACKUP_POD" ]; then
    echo "ERROR: No PostgreSQL pod found in namespace $NAMESPACE"
    exit 1
fi
echo "Using pod: $BACKUP_POD"

# Copy backups from PVC to local temp dir
echo ""
echo "Copying backups from PVC..."

# First, check what backups exist by running ls in the pod
# The backup cronjob creates files at /backup/
BACKUP_FILES=$($KUBECTL exec -n "$NAMESPACE" "$BACKUP_POD" -- ls -1 /backup/ 2>/dev/null | grep "pg_dumpall" || true)

if [ -z "$BACKUP_FILES" ]; then
    echo "No backup files found in /backup/"
    echo "The backup CronJob may not have run yet."
    echo ""
    echo "To run backup manually:"
    echo "  kubectl create job --from=cronjob/postgres-backup postgres-backup-manual -n database"
    exit 0
fi

echo "Found backups:"
echo "$BACKUP_FILES"
echo ""

# Copy each backup file
for file in $BACKUP_FILES; do
    echo "Copying $file..."
    $KUBECTL cp "$NAMESPACE/$BACKUP_POD:/backup/$file" "$LOCAL_BACKUP_DIR/$file" 2>/dev/null || {
        echo "WARNING: Failed to copy $file"
    }
done

# Verify local copies
echo ""
echo "Local backups:"
ls -lh "$LOCAL_BACKUP_DIR"/ 2>/dev/null || echo "No files copied"

# Sync to Google Drive
echo ""
echo "Syncing to Google Drive..."
rclone sync "$LOCAL_BACKUP_DIR/" "$REMOTE_NAME:$BACKUP_FOLDER/" \
    --progress \
    --stats-one-line \
    -v

# Verify remote
echo ""
echo "Google Drive contents:"
rclone ls "$REMOTE_NAME:$BACKUP_FOLDER/" 2>/dev/null || echo "Empty or error"

# Show Google Drive space
echo ""
echo "Google Drive usage:"
rclone about "$REMOTE_NAME:" 2>/dev/null | head -5 || echo "Could not retrieve"

# Cleanup local temp
rm -rf "$LOCAL_BACKUP_DIR"

echo ""
echo "========================================="
echo "Sync Complete"
echo "========================================="
echo ""
echo "Backups available at: $REMOTE_NAME:$BACKUP_FOLDER/"
echo ""
echo "To restore:"
echo "  rclone copy $REMOTE_NAME:$BACKUP_FOLDER/pg_dumpall_YYYYMMDD.sql.gz /tmp/"
echo "  gunzip /tmp/pg_dumpall_*.sql.gz"
echo "  psql -h <host> -U postgres -f /tmp/pg_dumpall_*.sql"
