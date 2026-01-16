#!/bin/bash
# Get automation state and last_triggered
source "$(dirname "$0")/../lib-sh/ha-api.sh"

AUTOMATION="${1:?Usage: $0 <automation_entity_id>}"
ha_get_state "$AUTOMATION" | jq '{state, last_triggered: .attributes.last_triggered, current_state: .attributes.current}'
