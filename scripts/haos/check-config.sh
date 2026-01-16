#!/bin/bash
# Check HA config validity
source "$(dirname "$0")/../lib-sh/ha-api.sh"

echo "=== Checking HA Config ==="
ha_call_service "homeassistant" "check_config" "{}"

# Check for errors in persistent notification
sleep 2
ha_get_state "persistent_notification.homeassistant_check_config" | jq -r '.attributes.message // "No errors"'
