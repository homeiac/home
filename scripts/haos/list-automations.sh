#!/bin/bash
# List HA automations, optionally filtered by prefix
# Usage: list-automations.sh [filter_prefix]
# Examples: list-automations.sh          # all automations
#           list-automations.sh package  # automations starting with "package"

source "$(dirname "$0")/../lib-sh/ha-api.sh"

FILTER="${1:-}"

if [[ -n "$FILTER" ]]; then
    ha_api_get "states" | \
        jq -r ".[] | select(.entity_id | startswith(\"automation.$FILTER\")) | \"\(.entity_id): \(.state)\""
else
    ha_api_get "states" | \
        jq -r '.[] | select(.entity_id | startswith("automation.")) | "\(.entity_id): \(.state)"'
fi
