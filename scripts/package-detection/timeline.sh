#!/bin/bash
# Build complete timeline of events

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../../proxmox/homelab/.env"

HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2)
HA_URL="http://192.168.4.240:8123"

echo "=== CURRENT TIME ==="
echo "Local (PST): $(date)"
echo "UTC:         $(date -u)"
echo ""

# Last 60 minutes
ONE_HOUR_AGO=$(date -u -v-60M +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null)

echo "=== COMPLETE TIMELINE (last 60 min) ==="
echo "All Package Detection automation events:"
echo ""

curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/logbook/$ONE_HOUR_AGO" 2>/dev/null | \
    jq -r '.[] | select(.name == "Package Detection" or .name == "Package Delivery Detection") | "\(.when | split(".")[0]) | \(.message // .state)"' 2>/dev/null | \
    while read line; do
        # Convert UTC to PST for readability
        utc_time=$(echo "$line" | cut -d'|' -f1 | tr -d ' ')
        message=$(echo "$line" | cut -d'|' -f2-)
        # Just show the time portion for clarity
        time_only=$(echo "$utc_time" | cut -d'T' -f2)
        echo "UTC $time_only |$message"
    done

echo ""
echo "=== NOTIFICATIONS SENT ==="
curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/logbook/$ONE_HOUR_AGO" 2>/dev/null | \
    jq -r '.[] | select(.message != null) | select(.message | test("EVENT:notify|Someone at door|Package Delivered"; "i")) | "\(.when | split(".")[0]) | \(.message)"' 2>/dev/null
