#!/bin/bash
# Enable TTS debug logging in HA
source "$(dirname "$0")/../lib-sh/ha-api.sh"

echo "Enabling verbose debug logging..."
ha_api_post "services/logger/set_level" '{
    "homeassistant.components.tts": "debug",
    "homeassistant.components.esphome": "debug",
    "homeassistant.components.assist_satellite": "debug",
    "homeassistant.components.media_player": "debug",
    "aioesphomeapi": "debug"
}'

echo ""
echo "Debug logging enabled. Run TTS test and check logs."
