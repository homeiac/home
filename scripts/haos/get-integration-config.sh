#!/bin/bash
# Get config entry details for a specific HA integration
# Usage: get-integration-config.sh <domain>
#
# Examples:
#   get-integration-config.sh ollama
#   get-integration-config.sh esphome
#   get-integration-config.sh mqtt

source "$(dirname "$0")/../lib-sh/ha-api.sh"

DOMAIN="${1:?Usage: $0 <domain>}"

ha_api_get "config/config_entries/entry" | \
    jq ".[] | select(.domain == \"$DOMAIN\")"
