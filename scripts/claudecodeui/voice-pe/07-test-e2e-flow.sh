#!/bin/bash
# Test full end-to-end approval flow (simulates ClaudeCodeUI via HA API)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

[[ -z "$HA_TOKEN" ]] && { echo "ERROR: HA_TOKEN not found"; exit 1; }

HA_URL="http://192.168.1.122:8123"

# Generate a test requestId
REQUEST_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')

echo "=== End-to-End Approval Test ==="
echo ""
echo "Request ID: $REQUEST_ID"
echo ""

# Publish approval request via HA MQTT service
echo "1. Publishing approval request via HA..."
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    "$HA_URL/api/services/mqtt/publish" \
    -d "{
      \"topic\": \"claude/approval-request\",
      \"payload\": \"{\\\"requestId\\\": \\\"$REQUEST_ID\\\", \\\"toolName\\\": \\\"Bash\\\", \\\"input\\\": {\\\"command\\\": \\\"rm -rf /tmp/test\\\", \\\"description\\\": \\\"Delete test files\\\"}, \\\"sessionId\\\": \\\"test-session\\\", \\\"sourceDevice\\\": \\\"test\\\"}\"
    }" >/dev/null

echo "✓ Request published"
echo ""
echo "Voice PE should now:"
echo "  - Show ORANGE LED"
echo "  - Say 'Approve or reject within 30 seconds'"
echo ""
echo "Rotate dial CW (approve) or CCW (reject)..."
echo ""
echo "Checking stored requestId..."
sleep 2
curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/states/input_text.claude_approval_request_id" | jq -r '.state'
