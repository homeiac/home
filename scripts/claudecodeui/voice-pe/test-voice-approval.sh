#!/bin/bash
# Test voice approval flow
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

[[ -f "$ENV_FILE" ]] && HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
[[ -z "$HA_TOKEN" ]] && { echo "ERROR: HA_TOKEN not found"; exit 1; }

HA_URL="${HA_URL:-http://192.168.1.122:8123}"

echo "=== Testing Voice Approval Flow ==="
echo ""

# Step 1: Send fake approval request
echo "1. Sending approval request via MQTT..."
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "claude/approval-request",
    "payload": "{\"requestId\": \"test-123\", \"message\": \"Should I restart frigate?\"}"
  }' \
  "$HA_URL/api/services/mqtt/publish"
echo ""

echo "2. Voice PE should:"
echo "   - LED → orange"
echo "   - Speak: 'Should I restart frigate?'"
echo "   - Start listening (no wake word needed)"
echo ""
echo "3. Say 'yes' or 'no' to approve/reject"
echo ""
echo "4. Check approval response was sent:"
echo "   mosquitto_sub -h mqtt.host -t 'claude/approval-response' -C 1"
