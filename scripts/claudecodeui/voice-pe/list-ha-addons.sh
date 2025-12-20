#!/bin/bash
# List all Home Assistant addons
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

HA_HOST="${HA_HOST:-homeassistant.maas}"

echo "=== Home Assistant Addons ==="
curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "http://$HA_HOST:8123/api/hassio/addons" 2>/dev/null | \
    jq -r '.data.addons[] | "\(.state)\t\(.name) (\(.slug))"' | sort
