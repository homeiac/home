#!/bin/bash
# Copy a file to HAOS VM via Proxmox qm guest exec
# Usage: copy-to-ha.sh <local_file> <ha_dest_path>
#
# Example:
#   ./copy-to-ha.sh ./voice_approval.yaml /mnt/data/supervisor/homeassistant/custom_sentences/en/voice_approval.yaml
set -e

PROXMOX_HOST="${PROXMOX_HOST:-root@chief-horse.maas}"
VMID="${VMID:-116}"

LOCAL_FILE="${1:?Usage: $0 <local_file> <ha_dest_path>}"
HA_DEST="${2:?Usage: $0 <local_file> <ha_dest_path>}"

if [[ ! -f "$LOCAL_FILE" ]]; then
    echo "ERROR: Local file not found: $LOCAL_FILE"
    exit 1
fi

# Get destination directory
HA_DIR=$(dirname "$HA_DEST")

echo "=== Copying to HAOS ==="
echo "Source: $LOCAL_FILE"
echo "Dest:   $HA_DEST"
echo ""

# Create destination directory
echo "Creating directory: $HA_DIR"
ssh "$PROXMOX_HOST" "qm guest exec $VMID -- mkdir -p '$HA_DIR'" 2>/dev/null | jq -r '.exitcode' || true

# Base64 encode content to avoid shell escaping issues
CONTENT=$(base64 < "$LOCAL_FILE")

# Write file via base64 decode
echo "Writing file..."
RESULT=$(ssh "$PROXMOX_HOST" "qm guest exec $VMID -- bash -c 'echo \"$CONTENT\" | base64 -d > \"$HA_DEST\"'" 2>/dev/null)
EXIT_CODE=$(echo "$RESULT" | jq -r '.exitcode // 1')

if [[ "$EXIT_CODE" == "0" ]]; then
    echo "Verifying..."
    VERIFY=$(ssh "$PROXMOX_HOST" "qm guest exec $VMID -- head -3 '$HA_DEST'" 2>/dev/null | jq -r '.["out-data"] // "error"')
    echo "$VERIFY"
    echo ""
    echo "Done."
else
    echo "ERROR: Write failed (exit code: $EXIT_CODE)"
    echo "$RESULT"
    exit 1
fi
