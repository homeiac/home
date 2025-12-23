#!/bin/bash
# Restore Frigate config from backup
# Usage: ./restore-config.sh [backup-file]
#        ./restore-config.sh --list   # list available backups
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="$SCRIPT_DIR/../k3s/doorbell-analysis"
NAMESPACE="frigate"
POD_CONFIG_PATH="/config/config.yml"

export KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"

if [[ "$1" == "--list" || -z "$1" ]]; then
    echo "Available backups (newest first):"
    echo ""
    for file in $(ls -t "$BACKUP_DIR"/config-backup-*.yml 2>/dev/null | head -10); do
        filename=$(basename "$file")
        # Extract key info: doorbell URL from go2rtc streams section
        doorbell_url=$(grep "rtsp://frigate" "$file" | head -1 | sed 's/.*@//' | sed 's/:554.*//')
        echo "  $filename"
        echo "    doorbell -> $doorbell_url"
        echo ""
    done
    if [[ -z "$1" ]]; then
        echo "Usage: $0 <backup-file>"
        echo "       $0 --list"
    fi
    exit 0
fi

BACKUP_FILE="$1"

# Allow just filename or full path
if [[ ! -f "$BACKUP_FILE" ]]; then
    BACKUP_FILE="$BACKUP_DIR/$1"
fi

if [[ ! -f "$BACKUP_FILE" ]]; then
    echo "ERROR: Backup file not found: $1"
    echo "Run '$0 --list' to see available backups"
    exit 1
fi

echo "=== Frigate Config Restore ==="
echo ""
echo "Backup: $(basename "$BACKUP_FILE")"
echo ""

# Get pod
POD=$(kubectl get pods -n "$NAMESPACE" -l app=frigate -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [[ -z "$POD" ]]; then
    echo "ERROR: No Frigate pod found"
    exit 1
fi
echo "Pod: $POD"

# Show what we're restoring
echo ""
echo "Config to restore:"
head -25 "$BACKUP_FILE" | sed 's/^/  /'
echo "  ..."
echo ""

read -p "Restore this config? [y/N] " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

# Copy to pod
echo ""
echo "Uploading config..."
kubectl cp "$BACKUP_FILE" "$NAMESPACE/$POD:$POD_CONFIG_PATH"

# Restart
echo "Restarting Frigate..."
kubectl rollout restart deployment/frigate -n "$NAMESPACE"

echo ""
echo "=== Done ==="
echo "Watch: kubectl get pods -n frigate -w"
