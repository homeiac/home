#!/bin/bash
# Create input_boolean.claude_awaiting_approval helper in Home Assistant
# This tracks when Claude Code is waiting for user approval via dial/button
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

# Load HA_TOKEN from .env
if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

if [[ -z "$HA_TOKEN" ]]; then
    echo "ERROR: HA_TOKEN not found in $ENV_FILE"
    exit 1
fi

HA_HOST="${HA_HOST:-homeassistant.maas}"
ENTITY_ID="input_boolean.claude_awaiting_approval"

echo "=== Creating Claude Code Approval Helper ==="
echo "Target: $HA_HOST"
echo "Entity: $ENTITY_ID"
echo ""

# Check if helper already exists
echo "Checking if helper exists..."
EXISTING=$(curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "http://$HA_HOST:8123/api/states/$ENTITY_ID" | jq -r '.state // "not_found"')

if [[ "$EXISTING" != "not_found" && "$EXISTING" != "null" ]]; then
    echo "✅ Helper already exists (state: $EXISTING)"
    echo ""
    echo "Current helper state:"
    curl -s -H "Authorization: Bearer $HA_TOKEN" \
        "http://$HA_HOST:8123/api/states/$ENTITY_ID" | jq '{entity_id, state, attributes}'
    exit 0
fi

echo "Helper not found, creating..."
echo ""

# Create input_boolean via config flow API (HA 2023+)
# Home Assistant uses config entries flow for helpers
CREATE_PAYLOAD='{
  "handler": "input_boolean",
  "show_advanced_options": false
}'

echo "Step 1: Initiating config flow for input_boolean..."
FLOW_RESULT=$(curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d "$CREATE_PAYLOAD" \
    "http://$HA_HOST:8123/api/config/config_entries/flow")

FLOW_ID=$(echo "$FLOW_RESULT" | jq -r '.flow_id // empty')

if [[ -z "$FLOW_ID" ]]; then
    echo "ERROR: Failed to initiate config flow"
    echo "$FLOW_RESULT" | jq '.' 2>/dev/null || echo "$FLOW_RESULT"
    echo ""
    echo "Alternative: Create helper manually via HA UI:"
    echo "  Settings → Devices & Services → Helpers → Create Helper → Toggle"
    echo "  Name: Claude Awaiting Approval"
    echo "  Entity ID: input_boolean.claude_awaiting_approval"
    exit 1
fi

echo "Flow ID: $FLOW_ID"
echo ""

# Complete the flow with helper details
COMPLETE_PAYLOAD='{
  "name": "Claude Awaiting Approval",
  "icon": "mdi:check-circle-outline",
  "initial_state": false
}'

echo "Step 2: Completing config flow..."
RESULT=$(curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d "$COMPLETE_PAYLOAD" \
    "http://$HA_HOST:8123/api/config/config_entries/flow/$FLOW_ID")

echo "API Response:"
echo "$RESULT" | jq '.' 2>/dev/null || echo "$RESULT"
echo ""

# Check if we got an entry_id (success) or error
ENTRY_ID=$(echo "$RESULT" | jq -r '.result.entry_id // empty')
if [[ -n "$ENTRY_ID" ]]; then
    echo "✅ Config entry created: $ENTRY_ID"
else
    ERROR=$(echo "$RESULT" | jq -r '.errors // empty')
    if [[ -n "$ERROR" && "$ERROR" != "null" ]]; then
        echo "⚠️  Flow returned errors: $ERROR"
    fi
fi

# Wait for reload
sleep 2

# Verify creation
echo ""
echo "Verifying helper creation..."
VERIFY=$(curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "http://$HA_HOST:8123/api/states/$ENTITY_ID")

if echo "$VERIFY" | jq -e '.entity_id' > /dev/null 2>&1; then
    echo "✅ Helper created successfully!"
    echo ""
    echo "Helper state:"
    echo "$VERIFY" | jq '{entity_id, state, attributes}'
else
    echo "❌ Helper creation failed or not found"
    echo "Response:"
    echo "$VERIFY" | jq '.'
    exit 1
fi

echo ""
echo "=== Creation Complete ==="
