#!/bin/bash
# Get entity state - generic tool for any entity
# Usage: get-entity-state.sh <entity_id>

source "$(dirname "$0")/../lib-sh/ha-api.sh"

ENTITY="${1:?Usage: $0 <entity_id>}"
ha_get_state "$ENTITY" | jq '.'
