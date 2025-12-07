#!/bin/bash
# Test Ollama conversation agent directly (bypassing pipeline)
# Usage: ./test-ollama-direct.sh "turn on Monitor"

set -e

COMMAND="${1:-turn on Monitor}"

# Load HA token
HA_TOKEN=$(grep "^HA_TOKEN=" ~/code/home/proxmox/homelab/.env | cut -d'=' -f2 | tr -d '"')
HA_URL="${HA_URL:-http://192.168.4.240:8123}"

echo "=== Testing Ollama Direct ==="
echo "Command: $COMMAND"
echo ""

RESPONSE=$(curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" \
  -H "Content-Type: application/json" \
  "$HA_URL/api/services/conversation/process?return_response" \
  -d "{
    \"text\": \"$COMMAND\",
    \"agent_id\": \"conversation.ollama_conversation\"
  }")

echo "Response: $(echo "$RESPONSE" | jq -r '.service_response.response.speech.plain.speech')"
echo "Type: $(echo "$RESPONSE" | jq -r '.service_response.response.response_type')"
echo "Success targets: $(echo "$RESPONSE" | jq -c '.service_response.response.data.success')"
echo "Changed states: $(echo "$RESPONSE" | jq -c '[.changed_states[].entity_id]')"
