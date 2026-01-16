#!/bin/bash
# Get last automation trace
source "$(dirname "$0")/../lib-sh/ha-api.sh"

AUTOMATION="${1:?Usage: $0 <automation_entity_id>}"

# Strip automation. prefix if present
AUTOMATION="${AUTOMATION#automation.}"

# Get trace list first
RESPONSE=$(ha_api_get "trace/debug/automation/$AUTOMATION")

# Check if valid JSON
if ! echo "$RESPONSE" | jq -e '.' > /dev/null 2>&1; then
    echo "ERROR: Invalid response from API"
    echo "$RESPONSE"
    exit 1
fi

TRACE_ID=$(echo "$RESPONSE" | jq -r '.[0].run_id // empty')

if [[ -z "$TRACE_ID" ]]; then
    echo "No traces found"
    exit 0
fi

echo "Last trace: $TRACE_ID"
echo ""

# Get the full trace
ha_api_get "trace/automation/$AUTOMATION/$TRACE_ID" | jq '.'
