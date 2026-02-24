#!/bin/bash
# Reload a specific HA config entry by domain or entry_id
# Usage: reload-config-entry.sh <domain|entry_id>
#
# Examples:
#   reload-config-entry.sh ollama           # reload by domain name
#   reload-config-entry.sh 01KDWN1FFY...   # reload by entry_id
#
# This reloads the config_entry (different from reload-integration.sh
# which reloads a domain's YAML config like automations/scripts).

source "$(dirname "$0")/../lib-sh/ha-api.sh"

INPUT="${1:?Usage: $0 <domain|entry_id>}"

# If input looks like a domain name (no uppercase hex), look up the entry_id
if [[ ! "$INPUT" =~ ^[0-9A-Z] ]]; then
    ENTRY_ID=$(ha_api_get "config/config_entries/entry" | \
        jq -r ".[] | select(.domain == \"$INPUT\") | .entry_id" | head -1)
    if [[ -z "$ENTRY_ID" || "$ENTRY_ID" == "null" ]]; then
        echo "ERROR: No config entry found for domain '$INPUT'"
        exit 1
    fi
    echo "Domain '$INPUT' → entry_id: $ENTRY_ID"
else
    ENTRY_ID="$INPUT"
fi

echo "Reloading config entry: $ENTRY_ID"
RESULT=$(ha_api_post "config/config_entries/entry/$ENTRY_ID/reload" '{}')
echo "$RESULT" | jq '.' 2>/dev/null || echo "$RESULT"

# Verify new state
sleep 2
STATE=$(ha_api_get "config/config_entries/entry" | \
    jq -r ".[] | select(.entry_id == \"$ENTRY_ID\") | .state")
echo "New state: $STATE"
