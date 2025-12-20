#!/bin/bash
# Enable TTS debug logging in HA
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../proxmox/homelab/.env"

[[ -f "$ENV_FILE" ]] && HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
[[ -z "$HA_TOKEN" ]] && { echo "ERROR: HA_TOKEN not found"; exit 1; }

HA_URL="${HA_URL:-http://192.168.1.122:8123}"

echo "Enabling verbose debug logging..."
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "homeassistant.components.tts": "debug",
    "homeassistant.components.esphome": "debug",
    "homeassistant.components.assist_satellite": "debug",
    "homeassistant.components.media_player": "debug",
    "aioesphomeapi": "debug"
  }' \
  "$HA_URL/api/services/logger/set_level"

echo ""
echo "Debug logging enabled. Run TTS test and check logs."
