#!/bin/bash
# Backup Frigate config from K8s deployment
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="$SCRIPT_DIR/doorbell-analysis"
mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_FILE="$BACKUP_DIR/config-backup-$TIMESTAMP.yml"

echo "=== Backing up Frigate Config ==="
KUBECONFIG=~/kubeconfig kubectl exec -n frigate deployment/frigate -- cat /config/config.yml > "$BACKUP_FILE" 2>/dev/null

if [[ -s "$BACKUP_FILE" ]]; then
    echo "✓ Saved: $BACKUP_FILE"
    echo "  Size: $(wc -c < "$BACKUP_FILE") bytes"

    # Show recent backups
    echo ""
    echo "Recent backups:"
    ls -lt "$BACKUP_DIR"/config-backup-*.yml 2>/dev/null | head -5 | awk '{print "  " $NF}'
else
    echo "✗ Backup failed"
    rm -f "$BACKUP_FILE"
    exit 1
fi
