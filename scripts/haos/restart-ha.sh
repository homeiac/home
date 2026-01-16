#!/bin/bash
# Restart Home Assistant via API
source "$(dirname "$0")/../lib-sh/ha-api.sh"

echo "Restarting Home Assistant..."
ha_call_service "homeassistant" "restart" "{}"
echo "Restart initiated. Wait ~60 seconds for HA to come back up."
