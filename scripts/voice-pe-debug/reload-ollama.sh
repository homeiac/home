#!/bin/bash
# Reload Ollama integration
# Use this after HA restart if tool calling stops working

set -e

# Load HA token
HA_TOKEN=$(grep "^HA_TOKEN=" ~/code/home/proxmox/homelab/.env | cut -d'=' -f2 | tr -d '"')
HA_URL="${HA_URL:-http://192.168.4.240:8123}"

echo "=== Reloading Ollama Integration ==="

# Get Ollama integration entry ID
OLLAMA_ENTRY=$(curl -s -H "Authorization: Bearer $HA_TOKEN" \
  "$HA_URL/api/config/config_entries/entry" | \
  jq -r '.[] | select(.domain == "ollama") | .entry_id' | head -1)

if [ -z "$OLLAMA_ENTRY" ]; then
  echo "ERROR: Ollama integration not found"
  exit 1
fi

echo "Entry ID: $OLLAMA_ENTRY"

# Reload it
RESULT=$(curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" \
  "$HA_URL/api/config/config_entries/entry/$OLLAMA_ENTRY/reload")

echo "Result: $RESULT"
echo ""
echo "Ollama integration reloaded. Wait a few seconds before testing."
