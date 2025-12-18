#!/bin/bash
# Test Piper TTS synthesis speed independently of Voice PE
# This isolates whether the bottleneck is Piper or the Voice PE streaming
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

if [[ -z "$HA_TOKEN" ]]; then
    echo "ERROR: HA_TOKEN not found in $ENV_FILE"
    exit 1
fi

MESSAGE="${1:-Testing piper synthesis speed for latency analysis}"

echo "=== Piper TTS Synthesis Speed Test ==="
echo "Message: $MESSAGE"
echo ""

# Test 1: TTS to Google speaker (HTTP URL fetch - fast path)
echo "1. Testing Piper → Google Speaker (HTTP path)..."
START=$(date +%s.%N)

curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{
        \"entity_id\": \"tts.piper\",
        \"media_player_entity_id\": \"media_player.family_room_wifi\",
        \"message\": \"$MESSAGE\"
    }" \
    "http://192.168.1.122:8123/api/services/tts/speak" > /dev/null

END=$(date +%s.%N)
GOOGLE_TIME=$(echo "$END - $START" | bc)
echo "   API response time: ${GOOGLE_TIME}s"
echo "   (Audio plays almost immediately after API returns)"
echo ""

sleep 3

# Test 2: TTS to Voice PE (ESPHome/Wyoming path - slow path)
echo "2. Testing Piper → Voice PE (ESPHome/Wyoming path)..."
START=$(date +%s.%N)

curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{
        \"entity_id\": \"assist_satellite.home_assistant_voice_09f5a3_assist_satellite\",
        \"message\": \"$MESSAGE\"
    }" \
    "http://192.168.1.122:8123/api/services/assist_satellite/announce" > /dev/null

END=$(date +%s.%N)
VOICEPE_TIME=$(echo "$END - $START" | bc)
echo "   API response time: ${VOICEPE_TIME}s"
echo "   (Audio takes much longer to fully play)"
echo ""

# Test 3: Raw TTS URL generation (synthesis only)
echo "3. Testing raw TTS synthesis (no playback)..."
START=$(date +%s.%N)

RESULT=$(curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{
        \"platform\": \"tts\",
        \"message\": \"$MESSAGE\",
        \"language\": \"en\"
    }" \
    "http://192.168.1.122:8123/api/tts_get_url" 2>&1)

END=$(date +%s.%N)
SYNTH_TIME=$(echo "$END - $START" | bc)
echo "   Synthesis time: ${SYNTH_TIME}s"
echo "   Result: $RESULT"
echo ""

echo "=== Analysis ==="
echo ""
echo "Google Speaker time: ${GOOGLE_TIME}s"
echo "Voice PE time:       ${VOICEPE_TIME}s"
echo "Raw synthesis time:  ${SYNTH_TIME}s"
echo ""

# Compare
if (( $(echo "$VOICEPE_TIME > $GOOGLE_TIME * 5" | bc -l) )); then
    echo "FINDING: Voice PE is >5x slower than Google Speaker"
    echo "         This indicates the bottleneck is in ESPHome/Wyoming streaming,"
    echo "         NOT in Piper synthesis."
else
    echo "FINDING: Times are comparable - bottleneck may be in Piper synthesis"
fi
