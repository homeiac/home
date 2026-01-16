#!/bin/bash
# Test TTS and show the URL being generated
source "$(dirname "$0")/../lib-sh/ha-api.sh"

MESSAGE="${1:-Test message}"

echo "=== Current HA URL Config ==="
ha_api_get "config" | jq -r '{internal_url, external_url}'

echo ""
echo "=== Generating TTS audio ==="
RESPONSE=$(ha_api_post "tts_get_url" "{\"platform\": \"piper\", \"message\": \"$MESSAGE\"}")

echo "TTS URL Response: $RESPONSE"

# Extract URL
TTS_URL=$(echo "$RESPONSE" | jq -r '.url // .path // "no url"')
echo ""
echo "=== TTS Audio URL ==="
echo "$TTS_URL"
