#!/bin/bash
# Simulate ClaudeCodeUI response to test automation
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

[[ -z "$HA_TOKEN" ]] && { echo "ERROR: HA_TOKEN not found"; exit 1; }

HA_URL="http://192.168.1.122:8123"

echo "=== Simulating ClaudeCodeUI Response ==="
echo ""

# This matches the structure from mqtt-bridge.js MQTTResponseWriter
PAYLOAD='{
  "type": "chunk",
  "content": {
    "type": "claude-response",
    "data": {
      "type": "assistant",
      "content": [
        {"type": "text", "text": "The answer is 4."}
      ]
    }
  },
  "session_id": "test-123",
  "source_device": "test",
  "timestamp": 1234567890
}'

echo "Payload structure:"
echo "$PAYLOAD" | jq .
echo ""

echo "Publishing to claude/home/response..."
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    "$HA_URL/api/services/mqtt/publish" \
    -d "{\"topic\": \"claude/home/response\", \"payload\": $(echo "$PAYLOAD" | jq -c . | jq -Rs .)}" >/dev/null

echo "✓ Published"
echo ""
echo "Voice PE should say: 'The answer is 4.'"
