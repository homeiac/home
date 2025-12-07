#!/bin/bash
# Full end-to-end test: check state, send command, verify change
# This is the definitive "did Ollama lie?" test

set -e

# Load HA token
HA_TOKEN=$(grep "^HA_TOKEN=" ~/code/home/proxmox/homelab/.env | cut -d'=' -f2 | tr -d '"')
HA_URL="${HA_URL:-http://192.168.4.240:8123}"
LIGHT="${LIGHT_ENTITY:-light.smart_dimmer_switch_2005093382991125581748e1e91baafc}"

echo "=== BEFORE ==="
STATE_BEFORE=$(curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/states/$LIGHT" | jq -r '.state')
NAME=$(curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/states/$LIGHT" | jq -r '.attributes.friendly_name')
echo "Light: $NAME ($LIGHT)"
echo "State: $STATE_BEFORE"

echo ""
echo "=== SENDING COMMAND ==="
if [ "$STATE_BEFORE" = "on" ]; then
  CMD="turn off $NAME"
else
  CMD="turn on $NAME"
fi

RESPONSE=$(curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" \
  -H "Content-Type: application/json" \
  "$HA_URL/api/services/conversation/process?return_response" \
  -d "{\"text\": \"$CMD\", \"agent_id\": \"conversation.ollama_conversation\"}")

echo "Command: $CMD"
echo "Response: $(echo "$RESPONSE" | jq -r '.service_response.response.speech.plain.speech')"
echo "Changed states: $(echo "$RESPONSE" | jq -c '[.changed_states[].entity_id]')"

sleep 2

echo ""
echo "=== AFTER ==="
STATE_AFTER=$(curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/states/$LIGHT" | jq -r '.state')
echo "State: $STATE_AFTER"

echo ""
echo "=== RESULT ==="
if [ "$STATE_BEFORE" != "$STATE_AFTER" ]; then
  echo "SUCCESS: Light state changed from $STATE_BEFORE to $STATE_AFTER"
else
  echo "FAILED: Light state unchanged (still $STATE_AFTER) - OLLAMA LIED!"
  exit 1
fi
