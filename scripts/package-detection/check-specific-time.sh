#!/bin/bash
# Check what happened at specific time window

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../../proxmox/homelab/.env"

HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2)
HA_URL="http://192.168.4.240:8123"

echo "=== Current time ==="
date
date -u

echo ""
echo "=== ALL events between 02:40-03:00 UTC (18:40-19:00 PST) ==="
echo ""

curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/logbook/2025-12-13T02:40:00Z" 2>/dev/null | \
    jq -r '.[] | "\(.when) | \(.name // .entity_id) | \(.message // .state)"' 2>/dev/null | \
    grep -iE "package|person|door|notify|walking|unknown|llm|vision|event.summary|mobile" | head -50
