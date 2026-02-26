#!/bin/bash
# Restore Frigate recordings from backup
# Usage: ./restore-recordings.sh [--dry-run] [CAMERA]
#
# Examples:
#   ./restore-recordings.sh                    # Restore all cameras
#   ./restore-recordings.sh backyard_hd        # Restore specific camera
#   ./restore-recordings.sh --dry-run          # Preview what would be restored
#
# Prerequisites:
#   - Mac with kubectl access (~/kubeconfig)
#   - SSH access to pumped-piglet.maas
#   - Frigate pod running

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="/local-3TB-backup/frigate-recordings"
DRY_RUN=""
CAMERA=""

# Parse args
while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN="true"
            shift
            ;;
        *)
            CAMERA="$1"
            shift
            ;;
    esac
done

export KUBECONFIG="${HOME}/kubeconfig"

echo "$(date): Starting Frigate recordings restore..."

# Check backup exists
if ! ssh root@pumped-piglet.maas "[ -d ${BACKUP_DIR} ]"; then
    echo "ERROR: Backup directory not found: ${BACKUP_DIR}"
    exit 1
fi

# List available backups
echo ""
echo "Available recordings on pumped-piglet:"
ssh root@pumped-piglet.maas "ls -la ${BACKUP_DIR}/"

BACKUP_SIZE=$(ssh root@pumped-piglet.maas "du -sh ${BACKUP_DIR}" | awk '{print $1}')
echo ""
echo "Total backup size: $BACKUP_SIZE"

# Get Frigate pod
POD=$(kubectl get pod -n frigate -l app=frigate -o jsonpath='{.items[0].metadata.name}')
if [ -z "$POD" ]; then
    echo "ERROR: No Frigate pod found"
    exit 1
fi

echo ""
echo "Frigate pod: $POD"

# Check current recordings in pod
echo ""
echo "Current recordings in Frigate pod:"
kubectl exec -n frigate "$POD" -- ls -la /media/frigate/recordings/ 2>/dev/null || echo "(empty)"

if [ -n "$DRY_RUN" ]; then
    echo ""
    echo "DRY RUN - would restore recordings from ${BACKUP_DIR}"
    if [ -n "$CAMERA" ]; then
        echo "  Camera: $CAMERA"
    else
        echo "  All cameras"
    fi
    exit 0
fi

# Confirm
echo ""
if [ -n "$CAMERA" ]; then
    read -p "Restore recordings for camera '$CAMERA'? (y/N) " -n 1 -r
else
    read -p "Restore ALL recordings? This will overwrite existing recordings. (y/N) " -n 1 -r
fi
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

# Restore by streaming tar from pumped-piglet through Mac to pod
echo ""
echo "Restoring recordings..."

if [ -n "$CAMERA" ]; then
    # Restore specific camera
    ssh root@pumped-piglet.maas "cd ${BACKUP_DIR} && tar cf - ${CAMERA}" \
        | kubectl exec -i -n frigate "$POD" -- tar xf - -C /media/frigate/recordings/
else
    # Restore all cameras
    ssh root@pumped-piglet.maas "cd ${BACKUP_DIR} && tar cf - ." \
        | kubectl exec -i -n frigate "$POD" -- tar xf - -C /media/frigate/recordings/
fi

# Verify
echo ""
echo "Restore complete. Current recordings:"
kubectl exec -n frigate "$POD" -- du -sh /media/frigate/recordings/
kubectl exec -n frigate "$POD" -- ls -la /media/frigate/recordings/
