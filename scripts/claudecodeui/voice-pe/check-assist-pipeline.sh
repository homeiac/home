#!/bin/bash
# Check Assist pipeline configuration (STT/TTS/LLM)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

HA_HOST="${HA_HOST:-homeassistant.maas}"

echo "=== Assist Pipeline Configuration ==="
echo ""

# Get all pipelines
echo "1. Available pipelines:"
curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"type": "assist_pipeline/pipeline/list"}' \
    "http://$HA_HOST:8123/api/websocket" 2>/dev/null || \
curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "http://$HA_HOST:8123/api/config" 2>/dev/null | jq '.components | map(select(. | test("tts|stt|assist")))'
echo ""

# Check TTS entities
echo "2. TTS entities:"
curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "http://$HA_HOST:8123/api/states" 2>/dev/null | \
    jq -r '.[] | select(.entity_id | startswith("tts.")) | "\(.entity_id): \(.state)"'
echo ""

# Check STT entities
echo "3. STT entities:"
curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "http://$HA_HOST:8123/api/states" 2>/dev/null | \
    jq -r '.[] | select(.entity_id | startswith("stt.")) | "\(.entity_id): \(.state)"'
echo ""

# Check Wyoming entities (Piper/Whisper)
echo "4. Wyoming entities:"
curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "http://$HA_HOST:8123/api/states" 2>/dev/null | \
    jq -r '.[] | select(.entity_id | test("wyoming|piper|whisper")) | "\(.entity_id): \(.state)"'
echo ""

# Check config entries for TTS
echo "5. TTS-related config entries:"
curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "http://$HA_HOST:8123/api/config/config_entries/entry" 2>/dev/null | \
    jq '.[] | select(.domain | test("tts|wyoming|piper|whisper|cloud")) | {domain, title, state}'
echo ""

# Check Voice PE satellite config
echo "6. Voice PE satellite attributes:"
curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "http://$HA_HOST:8123/api/states/assist_satellite.home_assistant_voice_09f5a3_assist_satellite" 2>/dev/null | \
    jq '.attributes'
