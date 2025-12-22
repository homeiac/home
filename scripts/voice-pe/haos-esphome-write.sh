#!/bin/bash
# Write content to file in ESPHome addon via base64 encoding
# Creates backup first
# Usage: ./haos-esphome-write.sh <local-file> <remote-path>
set -e

LOCAL_FILE="$1"
REMOTE_PATH="$2"

if [[ -z "$LOCAL_FILE" || -z "$REMOTE_PATH" ]]; then
    echo "Usage: $0 <local-file> <remote-path>"
    echo "Example: $0 ./configs/voice.yaml /config/esphome/voice.yaml"
    exit 1
fi

if [[ ! -f "$LOCAL_FILE" ]]; then
    echo "ERROR: Local file not found: $LOCAL_FILE"
    exit 1
fi

BACKUP_SUFFIX=$(date +%Y%m%d_%H%M%S)
REMOTE_BACKUP="${REMOTE_PATH}.backup-${BACKUP_SUFFIX}"

echo "=== ESPHome File Write ==="
echo "Local:  $LOCAL_FILE"
echo "Remote: $REMOTE_PATH"
echo ""

# Base64 encode the content
CONTENT_B64=$(base64 < "$LOCAL_FILE")

# Step 1: Backup existing file
echo "1. Creating backup..."
ssh root@chief-horse.maas "qm guest exec 116 -- docker exec addon_5c53de3b_esphome cp '$REMOTE_PATH' '$REMOTE_BACKUP'" 2>/dev/null || echo "   (no existing file)"

# Step 2: Write via base64 decode inside container
echo "2. Writing file via base64..."
ssh root@chief-horse.maas "qm guest exec 116 -- docker exec addon_5c53de3b_esphome sh -c 'echo $CONTENT_B64 | base64 -d > $REMOTE_PATH'"

# Step 3: Verify
echo "3. Verifying..."
REMOTE_LINES=$(ssh root@chief-horse.maas "qm guest exec 116 -- docker exec addon_5c53de3b_esphome wc -l < '$REMOTE_PATH'" 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('out-data','').strip())" 2>/dev/null || echo "?")
LOCAL_LINES=$(wc -l < "$LOCAL_FILE" | tr -d ' ')

echo "   Local lines:  $LOCAL_LINES"
echo "   Remote lines: $REMOTE_LINES"

echo ""
echo "Done."
