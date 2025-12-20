#!/bin/bash
# Test assist_satellite.start_conversation directly
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../proxmox/homelab/.env"

[[ -f "$ENV_FILE" ]] && HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
[[ -z "$HA_TOKEN" ]] && { echo "ERROR: HA_TOKEN not found"; exit 1; }

HA_URL="${HA_URL:-http://192.168.1.122:8123}"
MESSAGE="${1:-Hello, this is a test message. Say yes or no.}"

echo "=== Testing assist_satellite.start_conversation ==="
echo "Message: $MESSAGE"
echo ""

RESPONSE=$(curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"entity_id\": \"assist_satellite.home_assistant_voice_09f5a3_assist_satellite\",
    \"start_message\": \"$MESSAGE\"
  }" \
  "$HA_URL/api/services/assist_satellite/start_conversation")

echo "Response: $RESPONSE"
echo ""
echo "Voice PE should now speak and start listening."
