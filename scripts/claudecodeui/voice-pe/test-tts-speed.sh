#!/bin/bash
# Test TTS speed after model change
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

HA_HOST="${HA_HOST:-homeassistant.maas}"
MESSAGE="${1:-Testing the new faster voice model}"

echo "=== TTS Speed Test ==="
echo "Message: $MESSAGE"
echo ""

START=$(date +%s.%N)
echo "Triggering TTS at $(date +%H:%M:%S.%N)..."

curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{
        \"entity_id\": \"assist_satellite.home_assistant_voice_09f5a3_assist_satellite\",
        \"message\": \"$MESSAGE\"
    }" \
    "http://$HA_HOST:8123/api/services/assist_satellite/announce" > /dev/null

END=$(date +%s.%N)
API_TIME=$(echo "$END - $START" | bc)

echo "API returned at $(date +%H:%M:%S.%N)"
echo ""
echo "API response time: ${API_TIME}s"
echo "(Speech synthesis happens async - listen for actual playback)"
