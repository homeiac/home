#!/bin/bash
# Backup Frigate recordings from Mac via kubectl to pumped-piglet's 3TB ZFS
# Usage: ./backup-recordings-mac.sh [--dry-run]
#
# This script:
# 1. Tars recordings inside the Frigate pod
# 2. Streams the tarball via kubectl to the Mac
# 3. Pipes it directly to ssh on pumped-piglet for extraction
#
# No intermediate storage needed on Mac.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="/local-3TB-backup/frigate-recordings"
DATE=$(date +%Y%m%d)
DRY_RUN=${1:-}

export KUBECONFIG="${HOME}/kubeconfig"

echo "$(date): Starting Frigate recordings backup..."

# Get Frigate pod
POD=$(kubectl get pod -n frigate -l app=frigate -o jsonpath='{.items[0].metadata.name}')
if [ -z "$POD" ]; then
    echo "ERROR: No Frigate pod found"
    exit 1
fi

echo "Frigate pod: $POD"

# Check current recordings size
SIZE=$(kubectl exec -n frigate "$POD" -- du -sh /media/frigate/recordings 2>/dev/null | awk '{print $1}')
echo "Current recordings size: $SIZE"

if [ "$DRY_RUN" = "--dry-run" ]; then
    echo "DRY RUN - would backup recordings to ${BACKUP_DIR}"
    echo "Contents:"
    kubectl exec -n frigate "$POD" -- ls -la /media/frigate/recordings/
    exit 0
fi

# Ensure backup directory exists on pumped-piglet
ssh root@pumped-piglet.maas "mkdir -p ${BACKUP_DIR}"

# Stream tar from pod through Mac to pumped-piglet for extraction
# This avoids storing the full tarball on Mac
echo "Streaming recordings to pumped-piglet..."
kubectl exec -n frigate "$POD" -- tar cf - -C /media/frigate recordings \
    | ssh root@pumped-piglet.maas "cd ${BACKUP_DIR} && tar xf - --strip-components=1"

# Cleanup old recordings on backup (keep 7 days)
echo "Cleaning up old backups..."
ssh root@pumped-piglet.maas "find ${BACKUP_DIR} -type f -mtime +7 -delete 2>/dev/null || true"
ssh root@pumped-piglet.maas "find ${BACKUP_DIR} -type d -empty -delete 2>/dev/null || true"

# Report
BACKUP_SIZE=$(ssh root@pumped-piglet.maas "du -sh ${BACKUP_DIR}" | awk '{print $1}')
echo ""
echo "$(date): Backup complete"
echo "Location: pumped-piglet.maas:${BACKUP_DIR}"
echo "Backup size: $BACKUP_SIZE"
echo ""
echo "Backup contents:"
ssh root@pumped-piglet.maas "ls -la ${BACKUP_DIR}"
