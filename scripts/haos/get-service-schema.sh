#!/bin/bash
# Get schema for a specific HA service
source "$(dirname "$0")/../lib-sh/ha-api.sh"

domain="${1:-esphome}"
service="${2:-}"

if [[ -z "$service" ]]; then
    echo "Usage: $0 <domain> <service>"
    exit 1
fi

ha_api_get "services" | jq ".[] | select(.domain==\"$domain\") | .services[\"$service\"]"
