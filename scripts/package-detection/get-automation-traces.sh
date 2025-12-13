#!/bin/bash
# Get detailed automation traces for package detection
# Usage: ./get-automation-traces.sh [count]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../../proxmox/homelab/.env"

HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2)
HA_URL="http://192.168.4.240:8123"
COUNT="${1:-10}"

AUTOMATION_ID="automation.package_delivery_detection"

echo "=============================================="
echo "AUTOMATION TRACE ANALYSIS"
echo "=============================================="
echo ""

# List available traces
echo "--- Available Traces ---"
TRACE_LIST=$(curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/trace/$AUTOMATION_ID" 2>/dev/null)

if [ -z "$TRACE_LIST" ] || [ "$TRACE_LIST" = "null" ]; then
    echo "No traces found for $AUTOMATION_ID"
    echo ""
    echo "This means either:"
    echo "1. Automation has never triggered"
    echo "2. Traces have been cleared"
    echo "3. Automation entity ID is different"
    echo ""
    echo "Checking for alternate automation names..."
    curl -s -H "Authorization: Bearer $HA_TOKEN" \
        "$HA_URL/api/states" | \
        jq -r '.[] | select(.entity_id | contains("package") or contains("delivery")) | select(.entity_id | startswith("automation")) | .entity_id'
    exit 1
fi

echo "$TRACE_LIST" | jq -r ".[0:$COUNT] | .[] | \"Run ID: \(.run_id) | Start: \(.timestamp.start) | State: \(.state)\""
echo ""

# Get the most recent trace with full details
echo "--- Most Recent Trace Details ---"
LATEST_RUN_ID=$(echo "$TRACE_LIST" | jq -r '.[0].run_id')

if [ -n "$LATEST_RUN_ID" ] && [ "$LATEST_RUN_ID" != "null" ]; then
    echo "Fetching trace: $LATEST_RUN_ID"
    TRACE_DETAIL=$(curl -s -H "Authorization: Bearer $HA_TOKEN" \
        "$HA_URL/api/trace/$AUTOMATION_ID/$LATEST_RUN_ID" 2>/dev/null)

    echo ""
    echo "Trigger information:"
    echo "$TRACE_DETAIL" | jq '.trigger_info // .context.trigger // "No trigger info"' 2>/dev/null

    echo ""
    echo "Trace steps (showing key actions):"
    echo "$TRACE_DETAIL" | jq -r '.trace | to_entries[] | select(.key | contains("action") or contains("condition") or contains("choose")) | "\(.key): \(.value[0].result // .value[0].changed_variables // "executed")"' 2>/dev/null || echo "Unable to parse trace steps"
else
    echo "No run ID found"
fi
echo ""

# Check for any logbook entries
echo "--- Recent Logbook Entries (Package Detection) ---"
ONE_DAY_AGO=$(date -u -v-1d +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date -u -d '1 day ago' +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null)
curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/logbook/$ONE_DAY_AGO?entity=$AUTOMATION_ID" 2>/dev/null | \
    jq -r '.[0:20] | .[] | "\(.when): \(.name) - \(.message // .state)"' 2>/dev/null || echo "Unable to fetch logbook"
