#!/bin/bash
# Get HA addon info
source "$(dirname "$0")/../lib-sh/ha-api.sh"

ADDON="${1:?Usage: $0 <addon_slug>}"
RESPONSE=$(ha_api_get "hassio/addons/$ADDON/info")
echo "$RESPONSE" | jq '{state: .data.state, version: .data.version, name: .data.name}' 2>/dev/null || echo "$RESPONSE"
