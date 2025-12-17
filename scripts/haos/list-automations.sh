#!/bin/bash
# List HA automations, optionally filtered by prefix
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../proxmox/homelab/.env"

[[ -f "$ENV_FILE" ]] && HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
[[ -z "$HA_TOKEN" ]] && { echo "ERROR: HA_TOKEN not found in $ENV_FILE"; exit 1; }

FILTER="${1:-}"
HA_HOST="${HA_HOST:-homeassistant.maas:8123}"

if [[ -n "$FILTER" ]]; then
    curl -s -H "Authorization: Bearer $HA_TOKEN" "http://$HA_HOST/api/states" | \
        jq -r ".[] | select(.entity_id | startswith(\"automation.$FILTER\")) | \"\(.entity_id): \(.state)\""
else
    curl -s -H "Authorization: Bearer $HA_TOKEN" "http://$HA_HOST/api/states" | \
        jq -r '.[] | select(.entity_id | startswith("automation.")) | "\(.entity_id): \(.state)"'
fi
