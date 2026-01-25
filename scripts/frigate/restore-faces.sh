#!/bin/bash
# Restore Frigate face training images from pumped-piglet 3TB ZFS backup
#
# Usage: ./restore-faces.sh [YYYYMMDD]
#   If no date given, uses most recent backup
#
# Prerequisites:
#   - KUBECONFIG set or ~/kubeconfig exists
#   - SSH access to pumped-piglet.maas
#   - Frigate pod running
#
# Backup location: pumped-piglet.maas:/local-3TB-backup/frigate-backups/
# Backup schedule: Daily at 3am via cron on pumped-piglet
# Backup script: /root/scripts/backup-frigate-faces.sh (uses Frigate API)

set -e

BACKUP_DIR="/local-3TB-backup/frigate-backups"
KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"
export KUBECONFIG

# Get backup date from argument or find latest
if [ -n "$1" ]; then
    DATE="$1"
    BACKUP_FILE="frigate-faces-${DATE}.tar.gz"
else
    echo "Finding most recent backup..."
    BACKUP_FILE=$(ssh root@pumped-piglet.maas "ls -t ${BACKUP_DIR}/frigate-faces-*.tar.gz 2>/dev/null | head -1 | xargs basename")
    if [ -z "$BACKUP_FILE" ]; then
        echo "ERROR: No backups found in ${BACKUP_DIR}/"
        exit 1
    fi
fi

echo "=== Frigate Face Training Data Restore ==="
echo "Backup file: ${BACKUP_FILE}"
echo "Source: pumped-piglet.maas:${BACKUP_DIR}/"
echo ""

# Verify backup exists
if ! ssh root@pumped-piglet.maas "test -f ${BACKUP_DIR}/${BACKUP_FILE}"; then
    echo "ERROR: Backup file not found: ${BACKUP_DIR}/${BACKUP_FILE}"
    echo "Available backups:"
    ssh root@pumped-piglet.maas "ls -lh ${BACKUP_DIR}/"
    exit 1
fi

# Show backup info
echo "Backup details:"
ssh root@pumped-piglet.maas "ls -lh ${BACKUP_DIR}/${BACKUP_FILE}"
echo ""

# Check frigate pod is running
if ! kubectl get deploy frigate -n frigate &>/dev/null; then
    echo "ERROR: Frigate deployment not found. Is the cluster up?"
    exit 1
fi

POD=$(kubectl get pod -n frigate -l app=frigate -o jsonpath='{.items[0].metadata.name}')
if [ -z "$POD" ]; then
    echo "ERROR: No frigate pod found"
    exit 1
fi
echo "Target pod: ${POD}"
echo ""

# Confirm restore
read -p "This will OVERWRITE existing face data. Continue? [y/N] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

# Download backup
echo "Downloading backup..."
scp "root@pumped-piglet.maas:${BACKUP_DIR}/${BACKUP_FILE}" "/tmp/${BACKUP_FILE}"

# Extract locally first to get correct structure
echo "Extracting backup..."
cd /tmp
rm -rf faces-restore
mkdir faces-restore
tar xzf "${BACKUP_FILE}" -C faces-restore --strip-components=1

# Restore via Frigate API (POST /api/faces/{name})
echo "Restoring faces via Frigate API..."
FRIGATE_URL="https://frigate.app.home.panderosystems.com"

for FACE_DIR in faces-restore/*/; do
    FACE_NAME=$(basename "$FACE_DIR")
    [ "$FACE_NAME" = "train" ] && continue

    echo "  Restoring face: $FACE_NAME"
    for IMG in "$FACE_DIR"/*.webp; do
        [ -f "$IMG" ] || continue
        curl -sk -X POST "${FRIGATE_URL}/api/faces/${FACE_NAME}" \
            -F "file=@${IMG}" > /dev/null
    done
done

# Cleanup
rm -rf /tmp/faces-restore "/tmp/${BACKUP_FILE}"

# Verify restore
echo ""
echo "Restored face data:"
curl -sk "${FRIGATE_URL}/api/faces" | jq 'to_entries | .[] | "\(.key): \(.value | length) images"'

echo ""
echo "=== Restore complete ==="
echo "Frigate will use the restored face training data automatically."
echo "No restart required - embeddings are computed at runtime."
