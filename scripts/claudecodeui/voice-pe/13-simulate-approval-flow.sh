#!/bin/bash
# Simulate full approval flow: request -> capture -> dial -> response
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

[[ -z "$HA_TOKEN" ]] && { echo "ERROR: HA_TOKEN not found"; exit 1; }

HA_URL="http://192.168.1.122:8123"
REQUEST_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')

echo "=== Simulating Full Approval Flow ==="
echo ""
echo "Request ID: $REQUEST_ID"
echo ""

# Step 1: Simulate approval request (what ClaudeCodeUI sends)
echo "1. Publishing approval request..."
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    "$HA_URL/api/services/mqtt/publish" \
    -d "{\"topic\": \"claude/approval-request\", \"payload\": \"{\\\"requestId\\\": \\\"$REQUEST_ID\\\", \\\"toolName\\\": \\\"Bash\\\", \\\"input\\\": {\\\"command\\\": \\\"ls -la\\\", \\\"description\\\": \\\"List files\\\"}}\"}" >/dev/null
echo "   ✓ Published to claude/approval-request"

# Step 2: Check if HA captured the requestId
sleep 2
echo ""
echo "2. Checking HA captured requestId..."
CAPTURED_ID=$(curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/states/input_text.claude_approval_request_id" | jq -r '.state')
echo "   Stored ID: $CAPTURED_ID"
if [ "$CAPTURED_ID" == "$REQUEST_ID" ]; then
    echo "   ✓ MATCH!"
else
    echo "   ✗ MISMATCH! Expected: $REQUEST_ID"
fi

# Step 3: Check boolean state
echo ""
echo "3. Checking awaiting approval state..."
AWAITING=$(curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/states/input_boolean.claude_awaiting_approval" | jq -r '.state')
echo "   State: $AWAITING"

# Step 4: Simulate dial CW approval
echo ""
echo "4. Simulating dial CW approval..."
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    "$HA_URL/api/events/esphome.voice_pe_dial" \
    -d '{"direction": "clockwise"}' >/dev/null
echo "   ✓ Fired esphome.voice_pe_dial event"

# Step 5: Check what was published to approval-response
sleep 2
echo ""
echo "5. Checking final state..."
AWAITING_AFTER=$(curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/states/input_boolean.claude_awaiting_approval" | jq -r '.state')
echo "   Awaiting approval: $AWAITING_AFTER (should be 'off')"

echo ""
echo "=== Check ClaudeCodeUI logs for ==="
echo "    [MQTT Approval] === INCOMING RESPONSE ==="
echo "    requestId: $REQUEST_ID"
