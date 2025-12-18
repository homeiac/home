#!/bin/bash
# Check Voice PE entities in HA
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../proxmox/homelab/.env"
HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
HA_URL="http://192.168.1.122:8123"

echo "=== Voice PE Entities ==="
curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/states" | \
  jq -r '.[] | select(.entity_id | contains("voice_09f5a3")) | "\(.entity_id): \(.state)"'
