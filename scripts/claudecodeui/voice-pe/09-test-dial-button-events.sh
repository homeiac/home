#!/bin/bash
set -e

# Test dial and button events from Voice PE
# After ESPHome modification, this script helps verify events are firing correctly

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

# Source HA_TOKEN from .env
if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
    HA_URL=$(grep "^HA_URL=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

if [[ -z "$HA_TOKEN" ]] || [[ -z "$HA_URL" ]]; then
    echo "ERROR: HA_TOKEN or HA_URL not found in $ENV_FILE"
    exit 1
fi

HA_HOST="${HA_URL#http://}"
HA_HOST="${HA_HOST#https://}"
HA_HOST="${HA_HOST%%:*}"

echo "=================================================="
echo "Voice PE Dial & Button Event Test"
echo "=================================================="
echo ""
echo "Expected Events:"
echo "  - esphome.voice_pe_dial"
echo "    data: {direction: 'clockwise' | 'anticlockwise'}"
echo ""
echo "  - esphome.voice_pe_button"
echo "    data: {action: 'press' | 'long_press'}"
echo ""
echo "=================================================="
echo ""

# Function to check recent logbook events
check_recent_events() {
    echo "📋 Checking recent logbook events..."
    echo ""

    # Get events from last 5 minutes
    END_TIME=$(date -u +"%Y-%m-%dT%H:%M:%S")
    START_TIME=$(date -u -v-5M +"%Y-%m-%dT%H:%M:%S" 2>/dev/null || date -u -d '5 minutes ago' +"%Y-%m-%dT%H:%M:%S")

    EVENTS=$(curl -s -X GET \
        -H "Authorization: Bearer $HA_TOKEN" \
        -H "Content-Type: application/json" \
        "${HA_URL}/api/logbook/${START_TIME}?end_time=${END_TIME}" | \
        jq -r '.[] | select(.domain == "esphome" and (.message | contains("dial") or contains("button"))) |
               "[\(.when)] \(.name): \(.message)"' 2>/dev/null)

    if [[ -n "$EVENTS" ]]; then
        echo "Recent ESPHome Events:"
        echo "$EVENTS"
    else
        echo "No recent dial/button events found in logbook"
    fi
    echo ""
}

# Function to listen for events via websocket (alternative method)
listen_websocket_events() {
    echo "🔊 Starting websocket event listener..."
    echo "   (Press Ctrl+C to stop)"
    echo ""

    # Create a simple websocket listener using websocat if available
    if command -v websocat &> /dev/null; then
        WS_URL="${HA_URL/http/ws}/api/websocket"

        # Create auth message
        AUTH_MSG='{"type":"auth","access_token":"'$HA_TOKEN'"}'
        SUBSCRIBE_MSG='{"id":1,"type":"subscribe_events","event_type":"esphome.voice_pe_dial"}'
        SUBSCRIBE_MSG2='{"id":2,"type":"subscribe_events","event_type":"esphome.voice_pe_button"}'

        (
            echo "$AUTH_MSG"
            sleep 0.5
            echo "$SUBSCRIBE_MSG"
            echo "$SUBSCRIBE_MSG2"
            cat
        ) | websocat "$WS_URL" | \
            jq -r 'select(.type == "event") |
                   "\(.event.time_fired) | \(.event.event_type) | \(.event.data)"'
    else
        echo "⚠️  websocat not installed - websocket listening unavailable"
        echo "   Install with: brew install websocat"
        echo ""
    fi
}

# Function to show manual verification steps
show_manual_steps() {
    echo "📝 Manual Verification Steps:"
    echo ""
    echo "1. Open Home Assistant Developer Tools:"
    echo "   ${HA_URL}/developer-tools/events"
    echo ""
    echo "2. Listen for events:"
    echo "   - Event type: esphome.voice_pe_dial"
    echo "   - Event type: esphome.voice_pe_button"
    echo ""
    echo "3. Test physical device:"
    echo "   - Rotate dial clockwise/anticlockwise"
    echo "   - Press button (short press)"
    echo "   - Press and hold button (long press)"
    echo ""
    echo "4. Verify event data format:"
    echo "   Dial event should show: {direction: 'clockwise'} or {direction: 'anticlockwise'}"
    echo "   Button event should show: {action: 'press'} or {action: 'long_press'}"
    echo ""
}

# Function to test event firing via API
test_event_api() {
    echo "🧪 Testing event firing via API..."
    echo ""

    # Fire a test dial event
    echo "Firing test dial event (clockwise)..."
    RESPONSE=$(curl -s -X POST \
        -H "Authorization: Bearer $HA_TOKEN" \
        -H "Content-Type: application/json" \
        -d '{"direction": "clockwise"}' \
        "${HA_URL}/api/events/esphome.voice_pe_dial")

    if echo "$RESPONSE" | jq -e '.message == "Event esphome.voice_pe_dial fired."' > /dev/null 2>&1; then
        echo "✅ Dial event fired successfully"
    else
        echo "❌ Failed to fire dial event: $RESPONSE"
    fi

    sleep 1

    # Fire a test button event
    echo "Firing test button event (press)..."
    RESPONSE=$(curl -s -X POST \
        -H "Authorization: Bearer $HA_TOKEN" \
        -H "Content-Type: application/json" \
        -d '{"action": "press"}' \
        "${HA_URL}/api/events/esphome.voice_pe_button")

    if echo "$RESPONSE" | jq -e '.message == "Event esphome.voice_pe_button fired."' > /dev/null 2>&1; then
        echo "✅ Button event fired successfully"
    else
        echo "❌ Failed to fire button event: $RESPONSE"
    fi

    echo ""
}

# Function to query event history
query_event_history() {
    echo "📊 Querying event history..."
    echo ""

    # Query for dial events
    DIAL_COUNT=$(curl -s -X GET \
        -H "Authorization: Bearer $HA_TOKEN" \
        "${HA_URL}/api/history/period?filter_entity_id=event.voice_pe_dial&minimal_response" | \
        jq 'length' 2>/dev/null || echo "0")

    echo "Dial events in history: $DIAL_COUNT"

    # Query for button events
    BUTTON_COUNT=$(curl -s -X GET \
        -H "Authorization: Bearer $HA_TOKEN" \
        "${HA_URL}/api/history/period?filter_entity_id=event.voice_pe_button&minimal_response" | \
        jq 'length' 2>/dev/null || echo "0")

    echo "Button events in history: $BUTTON_COUNT"
    echo ""
}

# Main menu
while true; do
    echo "Choose an option:"
    echo "  1) Check recent logbook events"
    echo "  2) Fire test events via API"
    echo "  3) Query event history"
    echo "  4) Listen for events (websocket - requires websocat)"
    echo "  5) Show manual verification steps"
    echo "  6) Exit"
    echo ""
    read -p "Enter choice [1-6]: " choice

    case $choice in
        1)
            check_recent_events
            ;;
        2)
            test_event_api
            ;;
        3)
            query_event_history
            ;;
        4)
            listen_websocket_events
            ;;
        5)
            show_manual_steps
            ;;
        6)
            echo "Exiting..."
            exit 0
            ;;
        *)
            echo "Invalid choice"
            ;;
    esac

    echo ""
    echo "=================================================="
    echo ""
done
