#!/bin/bash
# Reset/backup/restore metrics data
# Usage: ./reset-metrics.sh [backup|restore|clean]

set -e

METRICS_DIR="$HOME/.claude/metrics"
BACKUP_DIR="$HOME/.claude/metrics-backup"

case "${1:-clean}" in
    backup)
        mkdir -p "$BACKUP_DIR"
        cp -r "$METRICS_DIR"/* "$BACKUP_DIR/" 2>/dev/null || true
        echo "Backed up to $BACKUP_DIR"
        ;;
    restore)
        if [[ -d "$BACKUP_DIR" ]]; then
            rm -f "$METRICS_DIR"/*.jsonl 2>/dev/null || true
            cp -r "$BACKUP_DIR"/* "$METRICS_DIR/" 2>/dev/null || true
            echo "Restored from $BACKUP_DIR"
        else
            echo "No backup found"
            exit 1
        fi
        ;;
    clean)
        rm -f "$METRICS_DIR"/*.jsonl 2>/dev/null || true
        mkdir -p "$METRICS_DIR"
        echo "Metrics cleaned"
        ;;
    *)
        echo "Usage: $0 [backup|restore|clean]"
        exit 1
        ;;
esac
