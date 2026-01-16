#!/bin/bash
# Home Assistant API Library
# Source this file in HA scripts for consistent API access
#
# Usage:
#   source "$(dirname "$0")/../lib/ha-api.sh"
#   ha_get_state "sensor.temperature"
#   ha_call_service "light" "turn_on" '{"entity_id": "light.living_room"}'
#
# Environment:
#   HA_URL   - Override default URL (optional)
#   HA_TOKEN - Override token loading (optional, loaded from .env if not set)

set -e

# Find repo root relative to this file
_HA_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_HA_REPO_ROOT="$(cd "$_HA_LIB_DIR/../.." && pwd)"

# Load HA_TOKEN from .env if not already set
if [[ -z "$HA_TOKEN" ]]; then
    _ENV_FILE="$_HA_REPO_ROOT/proxmox/homelab/.env"
    if [[ -f "$_ENV_FILE" ]]; then
        HA_TOKEN=$(grep "^HA_TOKEN=" "$_ENV_FILE" | cut -d'=' -f2- | tr -d '"')
    fi
fi

if [[ -z "$HA_TOKEN" ]]; then
    echo "ERROR: HA_TOKEN not found. Set HA_TOKEN env var or add to proxmox/homelab/.env" >&2
    exit 1
fi

# Default URL - use DNS name for consistency
# Note: Previous scripts used 192.168.1.122, 192.168.4.240, or homeassistant.maas
# Standardize on homeassistant.maas (resolves via MAAS DNS)
HA_URL="${HA_URL:-http://homeassistant.maas:8123}"

# Export for child processes
export HA_TOKEN HA_URL

#######################################
# Make a GET request to HA API
# Arguments:
#   $1 - API endpoint (without /api/ prefix)
# Returns:
#   JSON response on stdout
#######################################
ha_api_get() {
    local endpoint="${1:?Usage: ha_api_get <endpoint>}"
    curl -s --fail-with-body --max-time 30 \
        -H "Authorization: Bearer $HA_TOKEN" \
        "$HA_URL/api/$endpoint"
}

#######################################
# Make a POST request to HA API
# Arguments:
#   $1 - API endpoint (without /api/ prefix)
#   $2 - JSON payload (optional)
# Returns:
#   JSON response on stdout
#######################################
ha_api_post() {
    local endpoint="${1:?Usage: ha_api_post <endpoint> [json_payload]}"
    local payload="${2:-{}}"
    curl -s --fail-with-body --max-time 30 \
        -X POST \
        -H "Authorization: Bearer $HA_TOKEN" \
        -H "Content-Type: application/json" \
        -d "$payload" \
        "$HA_URL/api/$endpoint"
}

#######################################
# Get state of an entity
# Arguments:
#   $1 - Entity ID (e.g., sensor.temperature)
# Returns:
#   JSON state object on stdout
#######################################
ha_get_state() {
    local entity_id="${1:?Usage: ha_get_state <entity_id>}"
    ha_api_get "states/$entity_id"
}

#######################################
# Get just the state value of an entity
# Arguments:
#   $1 - Entity ID (e.g., sensor.temperature)
# Returns:
#   State value string on stdout
#######################################
ha_get_state_value() {
    local entity_id="${1:?Usage: ha_get_state_value <entity_id>}"
    ha_get_state "$entity_id" | jq -r '.state'
}

#######################################
# Call a Home Assistant service
# Arguments:
#   $1 - Domain (e.g., light, switch, script)
#   $2 - Service (e.g., turn_on, turn_off, reload)
#   $3 - JSON service data (optional)
# Returns:
#   JSON response on stdout
#######################################
ha_call_service() {
    local domain="${1:?Usage: ha_call_service <domain> <service> [json_data]}"
    local service="${2:?Usage: ha_call_service <domain> <service> [json_data]}"
    local data="${3:-{}}"
    ha_api_post "services/$domain/$service" "$data"
}

#######################################
# Turn on an entity
# Arguments:
#   $1 - Entity ID
# Returns:
#   JSON response on stdout
#######################################
ha_turn_on() {
    local entity_id="${1:?Usage: ha_turn_on <entity_id>}"
    local domain="${entity_id%%.*}"
    ha_call_service "$domain" "turn_on" "{\"entity_id\": \"$entity_id\"}"
}

#######################################
# Turn off an entity
# Arguments:
#   $1 - Entity ID
# Returns:
#   JSON response on stdout
#######################################
ha_turn_off() {
    local entity_id="${1:?Usage: ha_turn_off <entity_id>}"
    local domain="${entity_id%%.*}"
    ha_call_service "$domain" "turn_off" "{\"entity_id\": \"$entity_id\"}"
}

#######################################
# Set input_text value
# Arguments:
#   $1 - Entity ID (input_text.*)
#   $2 - Value to set
# Returns:
#   JSON response on stdout
#######################################
ha_set_input_text() {
    local entity_id="${1:?Usage: ha_set_input_text <entity_id> <value>}"
    local value="${2?Usage: ha_set_input_text <entity_id> <value>}"
    ha_call_service "input_text" "set_value" "{\"entity_id\": \"$entity_id\", \"value\": \"$value\"}"
}

#######################################
# List all services for a domain
# Arguments:
#   $1 - Domain (e.g., light, esphome)
# Returns:
#   Service names on stdout (one per line)
#######################################
ha_list_domain_services() {
    local domain="${1:?Usage: ha_list_domain_services <domain>}"
    ha_api_get "services" | jq -r ".[] | select(.domain == \"$domain\") | .services | keys[]"
}

#######################################
# Reload an integration/domain
# Arguments:
#   $1 - Domain to reload (e.g., script, automation, scene)
# Returns:
#   JSON response on stdout
#######################################
ha_reload() {
    local domain="${1:?Usage: ha_reload <domain>}"
    ha_call_service "$domain" "reload" "{}"
}

#######################################
# Check if HA API is healthy
# Returns:
#   0 if healthy, non-zero otherwise
#######################################
ha_is_healthy() {
    local result
    result=$(ha_api_get "" 2>/dev/null) || return 1
    echo "$result" | jq -e '.message == "API running."' >/dev/null 2>&1
}

#######################################
# Print HA connection info (for debugging)
#######################################
ha_debug_info() {
    echo "HA_URL: $HA_URL"
    echo "HA_TOKEN: ${HA_TOKEN:0:10}...(${#HA_TOKEN} chars)"
}
