#!/bin/bash
# Quick one-liner test: Does Ollama tool calling actually work?

set -e

HA_TOKEN=$(grep "^HA_TOKEN=" ~/code/home/proxmox/homelab/.env | cut -d'=' -f2 | tr -d '"')
HA_URL="${HA_URL:-http://192.168.4.240:8123}"
LIGHT="${LIGHT_ENTITY:-light.smart_dimmer_switch_2005093382991125581748e1e91baafc}"

BEFORE=$(curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/states/$LIGHT" | jq -r .state)

curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
  "$HA_URL/api/services/conversation/process" \
  -d '{"text":"toggle Monitor","agent_id":"conversation.ollama_conversation"}' > /dev/null

sleep 2

AFTER=$(curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/states/$LIGHT" | jq -r .state)

if [ "$BEFORE" != "$AFTER" ]; then
  echo "Before: $BEFORE | After: $AFTER | SUCCESS"
else
  echo "Before: $BEFORE | After: $AFTER | FAILED - OLLAMA LIED!"
  exit 1
fi
