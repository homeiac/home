#!/bin/bash
# Test TTS and show the URL being generated
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../proxmox/homelab/.env"

[[ -f "$ENV_FILE" ]] && HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
[[ -z "$HA_TOKEN" ]] && { echo "ERROR: HA_TOKEN not found"; exit 1; }

HA_URL="${HA_URL:-http://192.168.1.122:8123}"
MESSAGE="${1:-Test message}"

echo "=== Current HA URL Config ==="
curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/config" | jq -r '{internal_url, external_url}'

echo ""
echo "=== Generating TTS audio ==="
# Use tts.get_url to get the URL without playing
RESPONSE=$(curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"platform\": \"piper\",
    \"message\": \"$MESSAGE\"
  }" \
  "$HA_URL/api/tts_get_url")

echo "TTS URL Response: $RESPONSE"

# Extract URL
TTS_URL=$(echo "$RESPONSE" | jq -r '.url // .path // "no url"')
echo ""
echo "=== TTS Audio URL ==="
echo "$TTS_URL"
