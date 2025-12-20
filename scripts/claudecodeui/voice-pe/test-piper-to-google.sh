#!/bin/bash
# Test Piper TTS to Google speaker (not Voice PE)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

HA_HOST="${HA_HOST:-homeassistant.maas}"
MESSAGE="${1:-Testing piper to google speaker}"

echo "=== Piper to Google Speaker Test ==="
echo "Message: $MESSAGE"
echo ""

# Use tts.speak to Google speaker
echo "Sending to family_room_wifi (Google speaker)..."
START=$(date +%s.%N)

curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{
        \"entity_id\": \"tts.piper\",
        \"media_player_entity_id\": \"media_player.family_room_wifi\",
        \"message\": \"$MESSAGE\"
    }" \
    "http://$HA_HOST:8123/api/services/tts/speak" > /dev/null

END=$(date +%s.%N)
DURATION=$(echo "$END - $START" | bc)

echo "API returned in: ${DURATION}s"
echo ""
echo "If this is fast → Voice PE streaming is the bottleneck"
echo "If this is slow → Piper synthesis itself is slow"
