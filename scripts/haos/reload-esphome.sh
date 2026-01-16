#!/bin/bash
# Reload ESPHome integration to pick up new services
source "$(dirname "$0")/../lib-sh/ha-api.sh"

echo "=== Reloading ESPHome integration ==="
ha_api_post "services/homeassistant/reload_config_entry" '{"entry_id": ""}'

# Alternative: reload all integrations
echo "=== Reloading all config entries ==="
ha_call_service "homeassistant" "reload_all" "{}"

echo ""
echo "Done. Wait 10 seconds then test again."
