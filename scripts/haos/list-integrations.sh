#!/bin/bash
# List all Home Assistant integrations via API
source "$(dirname "$0")/../lib-sh/ha-api.sh"

echo "Fetching integrations from $HA_URL..."
ha_api_get "config/config_entries/entry" | jq -r '.[] | "\(.domain): \(.title)"' | sort
