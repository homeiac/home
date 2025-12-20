#!/bin/bash
# Test TTS directly to Voice PE media player
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../proxmox/homelab/.env"

[[ -f "$ENV_FILE" ]] && HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
[[ -z "$HA_TOKEN" ]] && { echo "ERROR: HA_TOKEN not found"; exit 1; }

HA_URL="${HA_URL:-http://192.168.1.122:8123}"
MESSAGE="${1:-Hello, this is a test of text to speech.}"

echo "=== Testing TTS Direct ==="
echo "Message: $MESSAGE"
echo ""

# Try assist_satellite.announce
echo "Trying assist_satellite.announce..."
RESPONSE=$(curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"entity_id\": \"assist_satellite.home_assistant_voice_09f5a3_assist_satellite\",
    \"message\": \"$MESSAGE\"
  }" \
  "$HA_URL/api/services/assist_satellite/announce")

echo "Response: $RESPONSE"
