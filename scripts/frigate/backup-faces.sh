#!/bin/bash
# Backup Frigate face training images to pumped-piglet 3TB ZFS pool
# Run from Mac or as a CronJob in K8s

set -e

BACKUP_DIR="/local-3TB-backup/frigate-backups"
DATE=$(date +%Y%m%d)
BACKUP_FILE="frigate-faces-${DATE}.tar.gz"
KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"

echo "$(date): Starting Frigate face backup..."

# Create backup from running pod
export KUBECONFIG
kubectl exec -n frigate deploy/frigate -- tar czf - /media/frigate/clips/faces 2>/dev/null > "/tmp/${BACKUP_FILE}"

# Copy to pumped-piglet
scp "/tmp/${BACKUP_FILE}" "root@pumped-piglet.maas:${BACKUP_DIR}/"

# Cleanup local temp
rm -f "/tmp/${BACKUP_FILE}"

# Keep only last 7 backups on pumped-piglet
ssh root@pumped-piglet.maas "cd ${BACKUP_DIR} && ls -t frigate-faces-*.tar.gz | tail -n +8 | xargs -r rm -f"

echo "$(date): Backup complete: ${BACKUP_DIR}/${BACKUP_FILE}"

# List current backups
ssh root@pumped-piglet.maas "ls -lh ${BACKUP_DIR}/"
