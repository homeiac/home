#!/bin/bash
# Get entity state
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../proxmox/homelab/.env"

[[ -f "$ENV_FILE" ]] && HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
[[ -z "$HA_TOKEN" ]] && { echo "ERROR: HA_TOKEN not found"; exit 1; }

ENTITY="${1:?Usage: $0 <entity_id>}"
HA_HOST="${HA_HOST:-homeassistant.maas:8123}"

curl -s -H "Authorization: Bearer $HA_TOKEN" "http://$HA_HOST/api/states/$ENTITY" | jq '.'
