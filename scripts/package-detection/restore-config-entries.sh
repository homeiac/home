#!/bin/bash
# Restore config_entries from backup

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

HA_URL="${HA_URL:-http://192.168.4.240:8123}"

echo "========================================================"
echo "  Restore config_entries from Backup"
echo "========================================================"
echo ""

# Find most recent backup
BACKUP_FILE=$(ls -t /tmp/core.config_entries.backup.* 2>/dev/null | head -1)

if [[ -z "$BACKUP_FILE" ]]; then
    echo "ERROR: No backup file found in /tmp/"
    exit 1
fi

echo "1. Using backup file: $BACKUP_FILE"
echo "   Size: $(wc -c < "$BACKUP_FILE") bytes"

echo ""
echo "2. Verifying backup contains Ollama..."
OLLAMA_COUNT=$(grep -c ollama "$BACKUP_FILE" || echo "0")
echo "   Ollama references: $OLLAMA_COUNT"

if [[ "$OLLAMA_COUNT" == "0" ]]; then
    echo "ERROR: Backup doesn't contain Ollama config!"
    exit 1
fi

echo ""
echo "3. Copying backup to Proxmox host..."
scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "$BACKUP_FILE" root@chief-horse.maas:/tmp/config_entries_restore.json

echo ""
echo "4. Writing file to HA VM (using a different method)..."
# Use a different approach - write to a tmp file first, then mv
timeout 60 ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null root@chief-horse.maas bash -c '
    # The file is on the Proxmox host at /tmp/config_entries_restore.json
    # We need to get it into the VM
    # Use qm guest exec to write chunks

    TARGET="/mnt/data/supervisor/homeassistant/.storage/core.config_entries"

    # First, encode to base64 on host
    BASE64=$(cat /tmp/config_entries_restore.json | base64 -w0)

    # Write base64 to VM tmp and decode there
    qm guest exec 116 -- bash -c "echo '\''$BASE64'\'' | base64 -d > /tmp/restore.json && mv /tmp/restore.json $TARGET"
'

echo ""
echo "5. Verifying restore..."
timeout 30 ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null root@chief-horse.maas \
    "qm guest exec 116 -- ls -la /mnt/data/supervisor/homeassistant/.storage/core.config_entries 2>/dev/null" 2>/dev/null | \
    jq -r '."out-data" // .'

OLLAMA_CHECK=$(timeout 30 ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null root@chief-horse.maas \
    "qm guest exec 116 -- grep -c ollama /mnt/data/supervisor/homeassistant/.storage/core.config_entries 2>/dev/null" 2>/dev/null | \
    jq -r '."out-data" // "0"')
echo "   Ollama references after restore: $OLLAMA_CHECK"

if [[ "$OLLAMA_CHECK" == "0" ]]; then
    echo ""
    echo "ERROR: Restore verification failed!"
    echo "Trying alternative method..."

    # Alternative: use scp with port forwarding or pvesm
    timeout 60 ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null root@chief-horse.maas bash -c '
        # Copy file to VM using qm guest exec with stdin
        CONTENT=$(cat /tmp/config_entries_restore.json)
        qm guest exec 116 input-data "$CONTENT" -- cat > /mnt/data/supervisor/homeassistant/.storage/core.config_entries
    ' 2>/dev/null || echo "Alternative method also failed"
fi

echo ""
echo "6. Restarting Home Assistant..."
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/services/homeassistant/restart" > /dev/null || echo "Could not restart via API"

echo ""
echo "   Waiting for HA to come back..."
for i in {1..60}; do
    sleep 5
    if curl -s --max-time 5 -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/" > /dev/null 2>&1; then
        echo "   HA is back online after ~$((i * 5)) seconds"
        break
    fi
    echo "   Still waiting... ($i/60)"
done

echo ""
echo "========================================================"
