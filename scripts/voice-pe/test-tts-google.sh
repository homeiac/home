#!/bin/bash
# Test TTS to Google Home speaker
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../proxmox/homelab/.env"

[[ -f "$ENV_FILE" ]] && HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
[[ -z "$HA_TOKEN" ]] && { echo "ERROR: HA_TOKEN not found"; exit 1; }

HA_URL="${HA_URL:-http://192.168.1.122:8123}"
MESSAGE="${1:-Testing TTS to Google Home speaker.}"

echo "=== Testing TTS to Google Home ==="
echo "Message: $MESSAGE"
echo ""

curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"entity_id\": \"tts.piper\",
    \"media_player_entity_id\": \"media_player.nikhil_bedroom_speaker\",
    \"message\": \"$MESSAGE\"
  }" \
  "$HA_URL/api/services/tts/speak"

echo ""
echo "Done."
