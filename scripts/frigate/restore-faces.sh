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

# Restore to pod
echo "Restoring to frigate pod..."
kubectl exec -n frigate "${POD}" -c frigate -- rm -rf /media/frigate/clips/faces
kubectl cp "/tmp/${BACKUP_FILE}" "frigate/${POD}:/tmp/${BACKUP_FILE}" -c frigate
kubectl exec -n frigate "${POD}" -c frigate -- tar xzf "/tmp/${BACKUP_FILE}" -C / --strip-components=0
kubectl exec -n frigate "${POD}" -c frigate -- rm -f "/tmp/${BACKUP_FILE}"

# Cleanup local temp
rm -f "/tmp/${BACKUP_FILE}"

# Verify restore
echo ""
echo "Restored face data:"
kubectl exec -n frigate "${POD}" -c frigate -- ls -la /media/frigate/clips/faces/

echo ""
echo "=== Restore complete ==="
echo "Frigate will use the restored face training data automatically."
echo "No restart required - embeddings are computed at runtime."
