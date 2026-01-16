#!/bin/bash
# Generic HA service caller
# Usage: call-service.sh <domain> <service> [json_data]
# Examples:
#   call-service.sh script reload
#   call-service.sh light turn_on '{"entity_id": "light.living_room"}'
#   call-service.sh input_boolean turn_off '{"entity_id": "input_boolean.test"}'

source "$(dirname "$0")/../lib-sh/ha-api.sh"

DOMAIN="${1:?Usage: $0 <domain> <service> [json_data]}"
SERVICE="${2:?Usage: $0 <domain> <service> [json_data]}"
DATA="${3:-{}}"

echo "Calling $DOMAIN.$SERVICE..."
ha_call_service "$DOMAIN" "$SERVICE" "$DATA" | jq '.'
