#!/bin/bash
# Reset the Voice PE satellite via HA announce service
# Usage: reset-voice-pe.sh [message]
#
# Sends an announce to the Voice PE which cycles its state
# from stuck-blue back to idle. Default message: "System reset"

source "$(dirname "$0")/../lib-sh/ha-api.sh"

MESSAGE="${1:-System reset}"
ENTITY="assist_satellite.home_assistant_voice_09f5a3_assist_satellite"

echo "Resetting Voice PE with message: '$MESSAGE'"
RESULT=$(ha_call_service "assist_satellite" "announce" \
    "{\"entity_id\": \"$ENTITY\", \"message\": \"$MESSAGE\"}")

STATE=$(echo "$RESULT" | jq -r '.[0].state' 2>/dev/null)
echo "Voice PE state: $STATE"
