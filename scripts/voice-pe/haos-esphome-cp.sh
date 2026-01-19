#!/bin/bash
# Copy file to ESPHome addon in HAOS
# Creates backup of existing file first, then copies local file over
# Usage: ./haos-esphome-cp.sh <local-file> <remote-path-in-container>
# Example: ./haos-esphome-cp.sh ./configs/voice.yaml /config/esphome/voice.yaml
set -e

LOCAL_FILE="$1"
REMOTE_PATH="$2"

if [[ -z "$LOCAL_FILE" || -z "$REMOTE_PATH" ]]; then
    echo "Usage: $0 <local-file> <remote-path-in-container>"
    echo "Example: $0 ./configs/home-assistant-voice-09f5a3.yaml /config/esphome/home-assistant-voice-09f5a3.yaml"
    exit 1
fi

if [[ ! -f "$LOCAL_FILE" ]]; then
    echo "ERROR: Local file not found: $LOCAL_FILE"
    exit 1
fi

BACKUP_SUFFIX=$(date +%Y%m%d_%H%M%S)
REMOTE_BACKUP="${REMOTE_PATH}.backup-${BACKUP_SUFFIX}"

echo "=== ESPHome File Copy ==="
echo "Local:  $LOCAL_FILE"
echo "Remote: $REMOTE_PATH"
echo ""

# Step 1: Backup existing file in container
echo "1. Creating backup: ${REMOTE_BACKUP}"
ssh root@chief-horse.maas "qm guest exec 116 -- docker exec addon_5c53de3b_esphome cp '$REMOTE_PATH' '$REMOTE_BACKUP'" 2>/dev/null || echo "   (no existing file to backup)"

# Step 2: Copy local file to Proxmox host
echo "2. Copying to Proxmox host..."
scp -q "$LOCAL_FILE" root@chief-horse.maas:/tmp/esphome-upload

# Step 3: Copy from Proxmox host into HAOS VM
echo "3. Copying into HAOS VM..."
ssh root@chief-horse.maas "cat /tmp/esphome-upload | qm guest exec 116 -- tee /tmp/esphome-upload > /dev/null"

# Step 4: Copy from HAOS VM into ESPHome container
echo "4. Copying into ESPHome container..."
ssh root@chief-horse.maas "qm guest exec 116 -- docker cp /tmp/esphome-upload addon_5c53de3b_esphome:$REMOTE_PATH"

# Step 5: Verify
echo "5. Verifying..."
REMOTE_SIZE=$(ssh root@chief-horse.maas "qm guest exec 116 -- docker exec addon_5c53de3b_esphome wc -c < '$REMOTE_PATH'" 2>/dev/null | python3 -c "import sys, json; print(json.load(sys.stdin).get('out-data', '').strip())" 2>/dev/null || echo "?")
LOCAL_SIZE=$(wc -c < "$LOCAL_FILE" | tr -d ' ')

echo "   Local size:  $LOCAL_SIZE bytes"
echo "   Remote size: $REMOTE_SIZE bytes"

# Cleanup
ssh root@chief-horse.maas "rm -f /tmp/esphome-upload" 2>/dev/null || true

echo ""
echo "Done. Backup saved as: $REMOTE_BACKUP"
