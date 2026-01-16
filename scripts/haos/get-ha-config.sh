#!/bin/bash
# Get HA full config including URLs
source "$(dirname "$0")/../lib-sh/ha-api.sh"

echo "=== HA Configuration ==="
ha_api_get "config" | jq '.'
