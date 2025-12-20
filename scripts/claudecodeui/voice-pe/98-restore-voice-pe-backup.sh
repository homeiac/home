#!/bin/bash
set -e

# Restore Voice PE ESPHome configuration from backup
# Lists available backups and provides instructions for manual restore

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUPS_DIR="$SCRIPT_DIR/backups"
DEVICE_NAME="home_assistant_voice_09f5a3"
ESPHOME_HOST="homeassistant.maas"
ESPHOME_PORT="6052"

echo "=== Voice PE Configuration Restore ==="
echo ""

# Check if backups directory exists
if [[ ! -d "$BACKUPS_DIR" ]]; then
    echo "ERROR: No backups directory found at $BACKUPS_DIR"
    echo "Run 00-backup-voice-pe-config.sh first to create a backup"
    exit 1
fi

# List available backups
BACKUPS=($(ls -1t "$BACKUPS_DIR"/voice-pe-*.yaml 2>/dev/null))

if [[ ${#BACKUPS[@]} -eq 0 ]]; then
    echo "ERROR: No backups found in $BACKUPS_DIR"
    echo "Run 00-backup-voice-pe-config.sh first to create a backup"
    exit 1
fi

echo "Available backups:"
echo ""
for i in "${!BACKUPS[@]}"; do
    BACKUP="${BACKUPS[$i]}"
    FILENAME=$(basename "$BACKUP")
    SIZE=$(du -h "$BACKUP" | cut -f1)
    MODIFIED=$(stat -f "%Sm" -t "%Y-%m-%d %H:%M:%S" "$BACKUP")
    echo "  [$i] $FILENAME"
    echo "      Size: $SIZE | Modified: $MODIFIED"

    # Show wake word config if present
    if grep -q "micro_wake_word:" "$BACKUP"; then
        WAKE_MODELS=$(grep -A 20 "micro_wake_word:" "$BACKUP" | grep "model:" | sed 's/^[ \t]*- model: //' | tr '\n' ', ' | sed 's/,$//')
        if [[ -n "$WAKE_MODELS" ]]; then
            echo "      Wake words: $WAKE_MODELS"
        fi
    fi
    echo ""
done

# Prompt for selection
read -p "Select backup to restore [0-$((${#BACKUPS[@]}-1))]: " SELECTION

if [[ ! "$SELECTION" =~ ^[0-9]+$ ]] || [[ "$SELECTION" -ge ${#BACKUPS[@]} ]]; then
    echo "ERROR: Invalid selection"
    exit 1
fi

SELECTED_BACKUP="${BACKUPS[$SELECTION]}"
echo ""
echo "Selected: $(basename "$SELECTED_BACKUP")"
echo ""

# Show restore instructions
echo "=== Restore Instructions ==="
echo ""
echo "ESPHome dashboard does not support automated config upload via API."
echo "Follow these manual steps to restore the configuration:"
echo ""
echo "1. Open ESPHome dashboard:"
echo "   http://$ESPHOME_HOST:$ESPHOME_PORT"
echo ""
echo "2. Find device: $DEVICE_NAME"
echo ""
echo "3. Click 'Edit' on the device"
echo ""
echo "4. Copy the backup config:"
echo "   cat \"$SELECTED_BACKUP\" | pbcopy"
echo "   (Backup copied to clipboard)"
echo ""
echo "5. Paste into ESPHome editor (replace all content)"
echo ""
echo "6. Click 'Save'"
echo ""
echo "7. Click 'Install' → 'Wirelessly'"
echo ""
echo "8. Monitor logs for successful flash"
echo ""

# Copy to clipboard if pbcopy available
if command -v pbcopy &> /dev/null; then
    cat "$SELECTED_BACKUP" | pbcopy
    echo "✓ Backup config copied to clipboard"
    echo ""
fi

# Offer to display config
read -p "Display full config? [y/N]: " SHOW_CONFIG

if [[ "$SHOW_CONFIG" =~ ^[Yy]$ ]]; then
    echo ""
    echo "=== Configuration Preview ==="
    cat "$SELECTED_BACKUP"
    echo ""
    echo "=== End Configuration ==="
fi

echo ""
echo "After restore, verify with:"
echo "  scripts/claudecodeui/voice-pe/01-check-voice-pe-status.sh"
