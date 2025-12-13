#!/bin/bash
# Find ALL automations that might send doorbell/person notifications

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../../proxmox/homelab/.env"

HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2)
HA_URL="http://192.168.4.240:8123"

echo "=== ALL DOORBELL/PERSON RELATED AUTOMATIONS ==="
echo ""

curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/states" | \
    jq -r '.[] | select(.entity_id | startswith("automation")) | select(.entity_id | test("door|person|reolink|motion|visitor|notify|delivery|package"; "i")) | "\(.entity_id): \(.state)"'

echo ""
echo "=== RECENT AUTOMATION TRIGGERS (last 30 min) ==="
THIRTY_MIN_AGO=$(date -u -v-30M +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null)

curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/logbook/$THIRTY_MIN_AGO" | \
    jq -r '.[] | select(.entity_id != null) | select(.entity_id | startswith("automation")) | "\(.when | split(".")[0]) | \(.entity_id) | \(.message // .state)"' 2>/dev/null | head -30

echo ""
echo "=== ALL NOTIFICATIONS SENT (last 30 min) ==="
curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/logbook/$THIRTY_MIN_AGO" | \
    jq -r '.[] | select(.domain == "notify" or (.message != null and (.message | test("notify|notification|mobile_app"; "i")))) | "\(.when | split(".")[0]) | \(.name) | \(.message // .state)"' 2>/dev/null | head -20
