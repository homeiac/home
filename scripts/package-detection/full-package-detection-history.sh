#!/bin/bash
# Get ALL Package Detection logs from last 3 hours

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../../proxmox/homelab/.env"

HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2)
HA_URL="http://192.168.4.240:8123"

THREE_HOURS_AGO=$(date -u -v-180M +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null)

echo "=== ALL PACKAGE DETECTION LOGS (last 3 hours) ==="
echo "Current time: $(date) / $(date -u)"
echo ""

curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/logbook/$THREE_HOURS_AGO" | \
    jq -r '.[] | select(.name == "Package Detection" or .name == "Package Delivery Detection") | "\(.when) | \(.message // .state)"' 2>/dev/null

echo ""
echo "=== NOTIFICATIONS (EVENT:notify) ==="
curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/logbook/$THREE_HOURS_AGO" | \
    jq -r '.[] | select(.message != null) | select(.message | test("EVENT:notify|Someone at door"; "i")) | "\(.when) | \(.name) | \(.message)"' 2>/dev/null
