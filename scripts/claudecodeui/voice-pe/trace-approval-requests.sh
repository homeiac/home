#!/bin/bash
# Trace all approval-request messages to debug requestId mismatch
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load MQTT creds
CCUI_ENV="/Users/10381054/code/claudecodeui/.env"
if [[ -f "$CCUI_ENV" ]]; then
    export $(grep -v '^#' "$CCUI_ENV" | xargs)
fi

MQTT_HOST="${MQTT_BROKER_URL#mqtt://}"
MQTT_HOST="${MQTT_HOST%:*}"
MQTT_HOST="${MQTT_HOST:-homeassistant.maas}"

echo "=== Tracing approval-request messages ==="
echo "Subscribing to claude/approval-request for 20 seconds..."
echo ""

# Subscribe and capture ALL messages
TRACE_FILE=$(mktemp)
timeout 20 mosquitto_sub -h "$MQTT_HOST" -u "$MQTT_USERNAME" -P "$MQTT_PASSWORD" \
    -t "claude/approval-request" -v > "$TRACE_FILE" 2>/dev/null &
SUB_PID=$!
sleep 2

# Send command that needs approval
echo "Sending command: delete /tmp/trace-test.txt"
mosquitto_pub -h "$MQTT_HOST" -u "$MQTT_USERNAME" -P "$MQTT_PASSWORD" \
    -t "claude/command" \
    -m '{"source":"trace-test","message":"delete /tmp/trace-test.txt","stream":false}'

echo "Waiting for messages..."
wait $SUB_PID 2>/dev/null || true

echo ""
echo "=== Messages captured ==="
if [[ -s "$TRACE_FILE" ]]; then
    cat "$TRACE_FILE"
    echo ""
    echo "=== RequestIds found ==="
    grep -o '"requestId":"[^"]*"' "$TRACE_FILE" | sort | uniq -c
else
    echo "(none)"
fi

rm -f "$TRACE_FILE"
