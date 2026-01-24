#!/bin/bash
# Check HA config validity
source "$(dirname "$0")/../lib-sh/ha-api.sh"

echo "=== Checking HA Config ==="

# Use the correct config check endpoint
RESULT=$(ha_api_post "config/core/check_config")

# Parse result
VALID=$(echo "$RESULT" | jq -r '.result // "unknown"')
ERRORS=$(echo "$RESULT" | jq -r '.errors // "none"')

if [[ "$VALID" == "valid" ]]; then
    echo "Config is valid"
    exit 0
else
    echo "Config check result: $VALID"
    echo "Errors: $ERRORS"
    exit 1
fi
