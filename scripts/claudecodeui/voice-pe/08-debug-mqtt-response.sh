#!/bin/bash
# Debug MQTT responses from ClaudeCodeUI
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

HA_URL="http://192.168.1.122:8123"

echo "=== Debug MQTT Response Format ==="
echo ""
echo "Subscribing to claude/home/response for 30 seconds..."
echo "Say 'ask claude what is 2 plus 2' to Voice PE"
echo ""

# Use HA's mqtt subscription via WebSocket is complex, let's check automation traces instead
echo "Checking recent automation traces for 'Claude Speak Response'..."
curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/states/automation.claude_speak_response" 2>/dev/null | jq '{state, last_triggered: .attributes.last_triggered}' || echo "Automation not found"

echo ""
echo "Check HA → Settings → Automations → Claude Speak Response → Traces"
