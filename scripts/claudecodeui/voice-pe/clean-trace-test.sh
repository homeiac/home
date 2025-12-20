#!/bin/bash
# Clean trace - ensure no overlap
set -e
CCUI_ENV="/Users/10381054/code/claudecodeui/.env"
[[ -f "$CCUI_ENV" ]] && export $(grep -v '^#' "$CCUI_ENV" | xargs)

MQTT_HOST="${MQTT_BROKER_URL#mqtt://}"
MQTT_HOST="${MQTT_HOST%:*}"

echo "=== Clean Trace Test ==="
echo "1. Waiting 5s for any pending commands to timeout..."
sleep 5

echo "2. Starting subscriber..."
TRACE_FILE=$(mktemp)
timeout 30 mosquitto_sub -h "$MQTT_HOST" -u "$MQTT_USERNAME" -P "$MQTT_PASSWORD" \
    -t "claude/approval-request" > "$TRACE_FILE" 2>/dev/null &
SUB_PID=$!
sleep 2

echo "3. Sending ONE command..."
mosquitto_pub -h "$MQTT_HOST" -u "$MQTT_USERNAME" -P "$MQTT_PASSWORD" \
    -t "claude/command" \
    -m '{"source":"clean-test","message":"delete /tmp/clean-trace-test.txt","stream":false}'

echo "4. Waiting 25s for any approval-requests..."
wait $SUB_PID 2>/dev/null || true

echo ""
echo "=== Approval-requests captured ==="
COUNT=$(wc -l < "$TRACE_FILE" | tr -d ' ')
echo "Count: $COUNT"
cat "$TRACE_FILE" | jq -r '.requestId' 2>/dev/null || cat "$TRACE_FILE"

rm -f "$TRACE_FILE"
