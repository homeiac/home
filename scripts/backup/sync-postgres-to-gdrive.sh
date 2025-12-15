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

# Check rclone in PATH or common locations
RCLONE="${RCLONE:-rclone}"
if ! command -v "$RCLONE" &>/dev/null; then
    if [ -x "$HOME/.local/bin/rclone" ]; then
        RCLONE="$HOME/.local/bin/rclone"
    else
        echo "ERROR: rclone not installed. Run install-rclone.sh first."
        exit 1
    fi
fi

# Check rclone remote
if ! $RCLONE listremotes 2>/dev/null | grep -q "^${REMOTE_NAME}:$"; then
    echo "ERROR: rclone remote '$REMOTE_NAME' not found."
    echo "Run setup-rclone-gdrive.sh to configure Google Drive."
    exit 1
fi

# Create local temp directory
mkdir -p "$LOCAL_BACKUP_DIR"

# The backup PVC is not mounted on the main postgres pod
# Create a helper pod to access the PVC
echo "Creating helper pod to access backup PVC..."

HELPER_POD="backup-helper-$$"

# Create helper pod
$KUBECTL apply -n "$NAMESPACE" -f - << EOF
apiVersion: v1
kind: Pod
metadata:
  name: $HELPER_POD
spec:
  containers:
  - name: helper
    image: busybox
    command: ["sleep", "300"]
    volumeMounts:
    - name: backup
      mountPath: /backup
  volumes:
  - name: backup
    persistentVolumeClaim:
      claimName: postgres-backup
  restartPolicy: Never
EOF

# Wait for pod to be ready
echo "Waiting for helper pod..."
$KUBECTL wait --for=condition=Ready pod/$HELPER_POD -n "$NAMESPACE" --timeout=60s

# List backups
BACKUP_FILES=$($KUBECTL exec -n "$NAMESPACE" $HELPER_POD -- ls -1 /backup/ 2>/dev/null | grep "pg_dumpall" || true)

if [ -z "$BACKUP_FILES" ]; then
    echo "No backup files found in PVC"
    $KUBECTL delete pod $HELPER_POD -n "$NAMESPACE" --ignore-not-found
    echo ""
    echo "To run backup manually:"
    echo "  $KUBECTL create job --from=cronjob/postgres-backup postgres-backup-manual -n database"
    exit 0
fi

echo "Found backups:"
echo "$BACKUP_FILES"
echo ""

# Copy each backup file using kubectl cp
for file in $BACKUP_FILES; do
    echo "Copying $file..."
    $KUBECTL cp "$NAMESPACE/$HELPER_POD:/backup/$file" "$LOCAL_BACKUP_DIR/$file" || {
        echo "WARNING: Failed to copy $file"
    }
done

# Cleanup helper pod
echo "Cleaning up helper pod..."
$KUBECTL delete pod $HELPER_POD -n "$NAMESPACE" --ignore-not-found

# Verify local copies
echo ""
echo "Local backups:"
ls -lh "$LOCAL_BACKUP_DIR"/ 2>/dev/null || echo "No files copied"

# Sync to Google Drive
echo ""
echo "Syncing to Google Drive..."
$RCLONE sync "$LOCAL_BACKUP_DIR/" "$REMOTE_NAME:$BACKUP_FOLDER/" \
    --progress \
    --stats-one-line \
    -v

# Verify remote
echo ""
echo "Google Drive contents:"
$RCLONE ls "$REMOTE_NAME:$BACKUP_FOLDER/" 2>/dev/null || echo "Empty or error"

# Show Google Drive space
echo ""
echo "Google Drive usage:"
$RCLONE about "$REMOTE_NAME:" 2>/dev/null | head -5 || echo "Could not retrieve"

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
