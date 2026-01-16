#!/bin/bash
# List ESPHome services registered in Home Assistant
source "$(dirname "$0")/../lib-sh/ha-api.sh"

filter="${1:-}"

echo "=== ESPHome Services ==="
ha_api_get "services" | \
  jq -r '.[] | select(.domain=="esphome") | .services | keys[]' | \
  if [[ -n "$filter" ]]; then grep -i "$filter"; else cat; fi
