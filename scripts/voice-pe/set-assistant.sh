#!/bin/bash
# Set Voice PE assistant pipeline
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../proxmox/homelab/.env"

[[ -f "$ENV_FILE" ]] && HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
[[ -z "$HA_TOKEN" ]] && { echo "ERROR: HA_TOKEN not found"; exit 1; }

HA_URL="${HA_URL:-http://192.168.1.122:8123}"
OPTION="${1:-Home Assistant}"

echo "Setting Voice PE assistant to: $OPTION"

curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"entity_id\": \"select.home_assistant_voice_09f5a3_assistant\",
    \"option\": \"$OPTION\"
  }" \
  "$HA_URL/api/services/select/select_option"

echo "Done."
