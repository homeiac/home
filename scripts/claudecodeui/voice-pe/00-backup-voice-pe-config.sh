#!/bin/bash
set -e

# Backup Voice PE ESPHome configuration
# Saves current YAML config to backups/ directory

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"
BACKUPS_DIR="$SCRIPT_DIR/backups"
DEVICE_NAME="home_assistant_voice_09f5a3"
ESPHOME_HOST="homeassistant.maas"
ESPHOME_PORT="6052"

# Load HA_TOKEN
if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

if [[ -z "$HA_TOKEN" ]]; then
    echo "ERROR: HA_TOKEN not found in $ENV_FILE"
    exit 1
fi

# Create backups directory
mkdir -p "$BACKUPS_DIR"

# Generate backup filename with timestamp
BACKUP_FILE="$BACKUPS_DIR/voice-pe-$(date +%Y-%m-%d-%H%M%S).yaml"

echo "=== Voice PE Configuration Backup ==="
echo "Device: $DEVICE_NAME"
echo "ESPHome: http://$ESPHOME_HOST:$ESPHOME_PORT"
echo ""

# Try to get config via ESPHome API (if available)
# ESPHome dashboard API endpoint: /download/<device_name>
DOWNLOAD_URL="http://$ESPHOME_HOST:$ESPHOME_PORT/download/$DEVICE_NAME"

echo "Attempting to download config from ESPHome dashboard..."
if curl -s -f -o "$BACKUP_FILE" "$DOWNLOAD_URL"; then
    echo "✓ Config saved to: $BACKUP_FILE"
    echo ""

    # Extract version info if available
    if grep -q "esphome:" "$BACKUP_FILE"; then
        echo "=== ESPHome Version Info ==="
        grep -A 2 "esphome:" "$BACKUP_FILE" || echo "(version not found in config)"
    fi

    # Show config summary
    echo ""
    echo "=== Config Summary ==="
    echo "Lines: $(wc -l < "$BACKUP_FILE")"
    echo "Size: $(du -h "$BACKUP_FILE" | cut -f1)"

    # Show microWakeWord config if present
    if grep -q "micro_wake_word:" "$BACKUP_FILE"; then
        echo ""
        echo "=== Wake Word Configuration ==="
        grep -A 10 "micro_wake_word:" "$BACKUP_FILE" | grep -E "model:|threshold:" || true
    fi

else
    echo "ERROR: Failed to download config from $DOWNLOAD_URL"
    echo ""
    echo "Troubleshooting:"
    echo "1. Verify ESPHome dashboard is running:"
    echo "   curl http://$ESPHOME_HOST:$ESPHOME_PORT"
    echo ""
    echo "2. Check device name is correct:"
    echo "   Should match ESPHome dashboard device list"
    echo ""
    echo "3. Manual backup via ESPHome UI:"
    echo "   http://$ESPHOME_HOST:$ESPHOME_PORT"
    echo "   Click device → Edit → Copy YAML"
    rm -f "$BACKUP_FILE"
    exit 1
fi

echo ""
echo "=== All Backups ==="
ls -lh "$BACKUPS_DIR"
