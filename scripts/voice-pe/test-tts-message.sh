#!/bin/bash
# Simple TTS test to Voice PE with timing
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

MESSAGE="${1:-Testing packet trace}"

echo "Message: $MESSAGE"
echo "Starting..."

START=$(date +%s.%N)

curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"entity_id\": \"assist_satellite.home_assistant_voice_09f5a3_assist_satellite\", \"message\": \"$MESSAGE\"}" \
    "http://192.168.1.122:8123/api/services/assist_satellite/announce" > /dev/null

END=$(date +%s.%N)
DURATION=$(echo "$END - $START" | bc)

echo "API returned in: ${DURATION}s"
