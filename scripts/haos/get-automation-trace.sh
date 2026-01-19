#!/bin/bash
# Debug HA automation: shows logbook history, current state, and full event chain around last trigger
# Usage: ./get-automation-trace.sh <automation_id> [count]
# Example: ./get-automation-trace.sh automation.greet_g_on_face_recognition

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../../proxmox/homelab/.env"

[[ -f "$ENV_FILE" ]] && HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2-)
[[ -z "$HA_TOKEN" ]] && { echo "ERROR: HA_TOKEN not found in $ENV_FILE"; exit 1; }

HA_URL="http://homeassistant.maas:8123"
AUTOMATION_ID="${1:-}"
COUNT="${2:-5}"

if [ -z "$AUTOMATION_ID" ]; then
    echo "Usage: $0 <automation_id> [count]"
    echo ""
    echo "Available automations:"
    curl -s -H "Authorization: Bearer $HA_TOKEN" \
        "$HA_URL/api/states" | \
        jq -r '.[] | select(.entity_id | startswith("automation.")) | .entity_id' | sort
    exit 1
fi

echo "=============================================="
echo "AUTOMATION TRACE: $AUTOMATION_ID"
echo "=============================================="
echo ""

# List available traces
echo "--- Recent Traces ---"
TRACE_LIST=$(curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/trace/$AUTOMATION_ID" 2>/dev/null)

# Check if trace API returns 404 (no traces stored)
if echo "$TRACE_LIST" | grep -q "404\|Not Found" || [ -z "$TRACE_LIST" ] || [ "$TRACE_LIST" = "null" ] || [ "$TRACE_LIST" = "[]" ]; then
    echo "No trace API data. Falling back to logbook..."
    echo ""
fi

# Always show logbook entries (more reliable)
echo "--- Logbook Entries (last 24h) ---"
ONE_DAY_AGO=$(date -u -v-1d '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || date -u -d '1 day ago' '+%Y-%m-%dT%H:%M:%SZ')
curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/logbook/$ONE_DAY_AGO?entity=$AUTOMATION_ID" | \
    jq -r ".[-$COUNT:] | .[] | \"\(.when): \(.message // .state)\"" 2>/dev/null || echo "No logbook entries"
echo ""

# Show automation state
echo "--- Automation State ---"
curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/states/$AUTOMATION_ID" | \
    jq '{state, last_triggered: .attributes.last_triggered, friendly_name: .attributes.friendly_name}' 2>/dev/null

# Show related events around last trigger
LAST_TRIGGERED=$(curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/states/$AUTOMATION_ID" | jq -r '.attributes.last_triggered' 2>/dev/null)

if [ -n "$LAST_TRIGGERED" ] && [ "$LAST_TRIGGERED" != "null" ]; then
    echo ""
    echo "--- Event Chain (around last trigger: $LAST_TRIGGERED) ---"
    # Extract just the datetime part without timezone/milliseconds
    TS="${LAST_TRIGGERED%+*}"
    TS="${TS%.*}"

    # macOS: parse as UTC, output as UTC
    # TZ=UTC forces interpretation as UTC
    EPOCH=$(TZ=UTC date -j -f "%Y-%m-%dT%H:%M:%S" "$TS" "+%s" 2>/dev/null)
    if [ -n "$EPOCH" ]; then
        START_EPOCH=$((EPOCH - 30))
        END_EPOCH=$((EPOCH + 60))
        START_TIME=$(TZ=UTC date -r $START_EPOCH "+%Y-%m-%dT%H:%M:%SZ")
        END_TIME=$(TZ=UTC date -r $END_EPOCH "+%Y-%m-%dT%H:%M:%SZ")
    else
        # Fallback
        START_TIME="$LAST_TRIGGERED"
        END_TIME=""
    fi

    if [ -n "$END_TIME" ]; then
        curl -s -H "Authorization: Bearer $HA_TOKEN" \
            "$HA_URL/api/logbook/$START_TIME?end_time=$END_TIME" | \
            jq -r '.[] | "\(.when): \(.entity_id) - \(.message // .state)"' 2>/dev/null | \
            grep -iE "greet|voice|face|assist|media|trendnet|living_room|frigate|motion|person|tts|piper" || echo "No related events found"
    fi
fi

# If traces exist, show them too
if ! echo "$TRACE_LIST" | grep -q "404\|Not Found" && [ -n "$TRACE_LIST" ] && [ "$TRACE_LIST" != "null" ] && [ "$TRACE_LIST" != "[]" ]; then
    echo ""
    echo "--- Trace Details ---"
    echo "$TRACE_LIST" | jq -r ".[0:$COUNT] | .[] | \"Run: \(.run_id) | \(.timestamp.start) | State: \(.state)\"" 2>/dev/null

    LATEST_RUN_ID=$(echo "$TRACE_LIST" | jq -r '.[0].run_id' 2>/dev/null)
    if [ -n "$LATEST_RUN_ID" ] && [ "$LATEST_RUN_ID" != "null" ]; then
        TRACE_DETAIL=$(curl -s -H "Authorization: Bearer $HA_TOKEN" \
            "$HA_URL/api/trace/$AUTOMATION_ID/$LATEST_RUN_ID" 2>/dev/null)

        echo ""
        echo "Trace steps:"
        echo "$TRACE_DETAIL" | jq -r '.trace | to_entries[] | "\(.key): \(.value[0].result.response // .value[0].error // "ok")"' 2>/dev/null || echo "Unable to parse"

        echo ""
        echo "Errors (if any):"
        echo "$TRACE_DETAIL" | jq '.trace | to_entries[] | select(.value[0].error != null) | {step: .key, error: .value[0].error}' 2>/dev/null || echo "None"
    fi
fi
