#!/bin/bash
# Test MQTT→LED flow end-to-end
# Publishes to MQTT topics and observes Voice PE LED behavior
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

# Load credentials from .env
if [[ -f "$ENV_FILE" ]]; then
    MQTT_USER="${MQTT_USER:-$(grep "^MQTT_USER=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')}"
    MQTT_PASS="${MQTT_PASS:-$(grep "^MQTT_PASS=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')}"
fi

if [[ -z "$MQTT_USER" || -z "$MQTT_PASS" ]]; then
    echo "ERROR: MQTT_USER or MQTT_PASS not found in $ENV_FILE"
    exit 1
fi

MQTT_HOST="${MQTT_HOST:-homeassistant.maas}"
MQTT_PORT="${MQTT_PORT:-1883}"

# Check if mosquitto_pub is available
if ! command -v mosquitto_pub &> /dev/null; then
    echo "ERROR: mosquitto_pub not found. Install with: brew install mosquitto"
    exit 1
fi

# Build auth args if credentials available
AUTH_ARGS=""
if [[ -n "$MQTT_USER" && -n "$MQTT_PASS" ]]; then
    AUTH_ARGS="-u $MQTT_USER -P $MQTT_PASS"
fi

publish_mqtt() {
    local topic="$1"
    local payload="$2"
    mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" $AUTH_ARGS -t "$topic" -m "$payload"
}

echo "=== MQTT→LED Flow Test ==="
echo "MQTT Broker: $MQTT_HOST:$MQTT_PORT"
echo ""
echo "Watch the Voice PE LED ring during this test!"
echo ""

# Test 1: Command → Thinking (cyan)
echo "Test 1: Publishing claude/command → LED should turn CYAN..."
publish_mqtt "claude/command" '{"command": "test", "source": "test-script"}'
echo "  Published! LED should be CYAN (thinking)"
sleep 3

# Test 2: Response complete → LED off
echo ""
echo "Test 2: Publishing response complete → LED should turn OFF..."
publish_mqtt "claude/home/response" '{"type": "complete", "content": "Test complete"}'
echo "  Published! LED should be OFF"
sleep 2

# Test 3: Approval request → Waiting (amber)
echo ""
echo "Test 3: Publishing approval-request → LED should turn AMBER..."
publish_mqtt "claude/approval-request" '{"tool": "Bash", "description": "Run test command"}'
echo "  Published! LED should be AMBER (waiting)"
sleep 3

# Test 4: Approval approved → Green, then off
echo ""
echo "Test 4: Publishing approval-response approved → LED should turn GREEN..."
publish_mqtt "claude/approval-response" '{"approved": true}'
echo "  Published! LED should be GREEN, then OFF after 2s"
sleep 4

# Test 5: Start another approval flow
echo ""
echo "Test 5: Publishing approval-request → LED should turn AMBER..."
publish_mqtt "claude/approval-request" '{"tool": "Edit", "description": "Edit file"}'
echo "  Published! LED should be AMBER (waiting)"
sleep 3

# Test 6: Approval rejected → Red, then off
echo ""
echo "Test 6: Publishing approval-response rejected → LED should turn RED..."
publish_mqtt "claude/approval-response" '{"approved": false}'
echo "  Published! LED should be RED, then OFF after 2s"
sleep 4

echo ""
echo "=== Test Complete ==="
echo ""
echo "Expected LED sequence:"
echo "  1. CYAN (3s) - thinking"
echo "  2. OFF"
echo "  3. AMBER (3s) - waiting"
echo "  4. GREEN (2s) - approved"
echo "  5. OFF"
echo "  6. AMBER (3s) - waiting"
echo "  7. RED (2s) - rejected"
echo "  8. OFF"
echo ""
echo "If LED didn't respond, check:"
echo "  - HA automation is enabled: automation.claude_code_led_feedback"
echo "  - MQTT credentials in .env (MQTT_USER, MQTT_PASS)"
echo "  - HA logs for automation traces"
