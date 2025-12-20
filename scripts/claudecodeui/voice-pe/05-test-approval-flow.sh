#!/bin/bash
# Test the Claude approval flow
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

[[ -z "$HA_TOKEN" ]] && { echo "ERROR: HA_TOKEN not found"; exit 1; }

HA_URL="http://192.168.1.122:8123"

echo "=== Testing Claude Approval Flow ==="
echo ""
echo "Triggering approval request..."
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    "$HA_URL/api/services/input_boolean/turn_on" \
    -d '{"entity_id": "input_boolean.claude_awaiting_approval"}' >/dev/null

echo "✓ Approval request sent!"
echo ""
echo "Voice PE should now:"
echo "  - Show ORANGE LED"
echo "  - Say 'Approve or reject within 30 seconds'"
echo ""
echo "Rotate dial:"
echo "  - CW = GREEN + 'Approved'"
echo "  - CCW = RED + 'Rejected'"
echo "  - Wait 30s = RED + 'Request timed out'"
