#!/bin/bash
# Check Assist pipeline TTS configuration via core storage
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

HA_HOST="${HA_HOST:-homeassistant.maas}"

echo "=== Assist TTS Configuration ==="

# Get assist pipeline storage via qm guest exec
echo "1. Reading assist_pipeline storage from HAOS VM..."
ssh root@chief-horse.maas "qm guest exec 116 -- cat /config/.storage/assist_pipeline" 2>/dev/null | \
    jq -r '.["out-data"]' | jq '.' 2>/dev/null || echo "Could not read assist_pipeline storage"

echo ""
echo "2. Checking core.config_entries for wyoming/piper..."
ssh root@chief-horse.maas "qm guest exec 116 -- cat /config/.storage/core.config_entries" 2>/dev/null | \
    jq -r '.["out-data"]' | jq '.data.entries[] | select(.domain == "wyoming") | {title, data}' 2>/dev/null || echo "Could not read config entries"
