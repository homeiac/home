#!/bin/bash
# Check if Home Assistant API is responding
# HAOS has NO SSH - use API or qm guest exec

source "$(dirname "$0")/../lib-sh/ha-api.sh"

echo "Checking Home Assistant API at $HA_URL..."
if ha_is_healthy; then
    echo "API is healthy"
    ha_api_get "" | jq .
else
    echo "ERROR: API is not responding"
    exit 1
fi
