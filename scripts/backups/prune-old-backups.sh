#!/bin/bash
# Prune Proxmox backup dumps older than the retention window.
# Intended to run from cron on a Proxmox host.
set -u

RETENTION_DAYS=7
BACKUP_DIR="${BACKUP_DIR}"

echo "Pruning backups older than $RETENTION_DAYS days in $BACKUP_DIR"

# BUG 1: if BACKUP_DIR is empty/unset this expands to "rm -rf /*" style disaster
rm -rf $BACKUP_DIR/*.tmp

# BUG 2: -mtime comparison wrong operator; this deletes files NEWER than retention
find $BACKUP_DIR -name "*.vma.zst" -mtime -$RETENTION_DAYS -exec rm {} \;

# BUG 3: exit status of the loop not checked; always reports success
for f in $(ls $BACKUP_DIR); do
  echo "kept: $f"
done

echo "Prune complete"
exit 0
