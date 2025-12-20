#!/bin/bash
# Test Piper TTS speed without Voice PE (to media player or just synthesis)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

HA_HOST="${HA_HOST:-homeassistant.maas}"
MESSAGE="${1:-Testing piper synthesis speed without voice pe}"

echo "=== Piper-Only TTS Test ==="
echo "Message: $MESSAGE"
echo ""

# Test 1: Use tts.speak service (generates audio, doesn't play on Voice PE)
echo "1. Testing tts.speak (synthesis only, no playback)..."
START=$(date +%s.%N)

# This generates audio but we need a media_player - let's check what's available
echo "   Finding media players..."
PLAYERS=$(curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "http://$HA_HOST:8123/api/states" | \
    jq -r '.[] | select(.entity_id | startswith("media_player.")) | .entity_id' | head -5)
echo "   Available: $PLAYERS"

echo ""
echo "2. Testing raw TTS get_url (synthesis timing)..."
START=$(date +%s.%N)

# Call tts.get_url which synthesizes and returns URL (measures pure synthesis time)
RESULT=$(curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{
        \"platform\": \"tts\",
        \"message\": \"$MESSAGE\",
        \"language\": \"en\"
    }" \
    "http://$HA_HOST:8123/api/tts_get_url" 2>&1)

END=$(date +%s.%N)
DURATION=$(echo "$END - $START" | bc)

echo "   Result: $RESULT"
echo "   Synthesis time: ${DURATION}s"
echo ""

# Test 3: Direct announce to Voice PE for comparison
echo "3. Testing assist_satellite.announce (full pipeline)..."
START=$(date +%s.%N)

curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{
        \"entity_id\": \"assist_satellite.home_assistant_voice_09f5a3_assist_satellite\",
        \"message\": \"$MESSAGE\"
    }" \
    "http://$HA_HOST:8123/api/services/assist_satellite/announce" > /dev/null

END=$(date +%s.%N)
DURATION=$(echo "$END - $START" | bc)

echo "   Full pipeline time: ${DURATION}s"
echo ""
echo "If synthesis is fast but full pipeline is slow → bottleneck is Voice PE streaming"
