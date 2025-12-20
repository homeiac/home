#!/bin/bash
# Set Voice PE volume
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../proxmox/homelab/.env"

[[ -f "$ENV_FILE" ]] && HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
[[ -z "$HA_TOKEN" ]] && { echo "ERROR: HA_TOKEN not found"; exit 1; }

HA_URL="${HA_URL:-http://192.168.1.122:8123}"
VOLUME="${1:-0.7}"

echo "Setting Voice PE volume to $VOLUME"

curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"entity_id\": \"media_player.home_assistant_voice_09f5a3_media_player\",
    \"volume_level\": $VOLUME
  }" \
  "$HA_URL/api/services/media_player/volume_set"

echo "Done."
