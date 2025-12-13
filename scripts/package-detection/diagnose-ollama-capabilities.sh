#!/bin/bash
# Phase 1: Diagnose Ollama capabilities for Voice PE notification system
# This script tests what's actually broken before applying fixes

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

HA_URL="${HA_URL:-http://192.168.4.240:8123}"

if [[ -z "$HA_TOKEN" ]]; then
    echo "ERROR: HA_TOKEN not found in $ENV_FILE"
    exit 1
fi

echo "========================================================"
echo "  Phase 1: Diagnosing Ollama Capabilities"
echo "========================================================"
echo ""
echo "Testing what's broken before applying fixes..."
echo ""

# Generate unique test value to detect hallucination
TEST_VALUE="DIAG-$(date +%s)-UNIQUE"

echo "========================================================"
echo "  TEST 1: Can Ollama read entity states?"
echo "========================================================"
echo ""

# Set a unique test value
echo "[1a] Setting unique test value: $TEST_VALUE"
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    -d "{\"entity_id\": \"input_text.pending_notification_message\", \"value\": \"$TEST_VALUE\"}" \
    "$HA_URL/api/services/input_text/set_value" > /dev/null

# Verify it was set
ACTUAL_VALUE=$(curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/states/input_text.pending_notification_message" | jq -r '.state')
echo "[1b] Verified entity value: $ACTUAL_VALUE"

# Ask Ollama about the value
echo "[1c] Asking Ollama: 'what is the value of input_text.pending_notification_message'"
RESPONSE=$(curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    -d '{"text": "what is the value of input_text.pending_notification_message", "language": "en"}' \
    "$HA_URL/api/conversation/process")

SPEECH=$(echo "$RESPONSE" | jq -r '.response.speech.plain.speech // "N/A"')
echo "[1d] Ollama response: $SPEECH"
echo ""

# Check if response contains the test value
if echo "$SPEECH" | grep -q "$TEST_VALUE"; then
    echo "RESULT: PASS - Ollama CAN read entity states"
    STATE_READING="PASS"
else
    echo "RESULT: FAIL - Ollama returned garbage (stale state bug confirmed)"
    STATE_READING="FAIL"
fi

echo ""
echo "========================================================"
echo "  TEST 2: Can Ollama call scripts/services?"
echo "========================================================"
echo ""

# Get current last_triggered time
BEFORE_TRIGGERED=$(curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/states/script.get_pending_notification" | jq -r '.attributes.last_triggered // "never"')
echo "[2a] Script last_triggered before: $BEFORE_TRIGGERED"

# Turn on notification flag so script has something to do
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    -d '{"entity_id": "input_boolean.has_pending_notification"}' \
    "$HA_URL/api/services/input_boolean/turn_on" > /dev/null

# Ask Ollama to call the script
echo "[2b] Asking Ollama: 'call script.get_pending_notification'"
RESPONSE=$(curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    -d '{"text": "call script.get_pending_notification", "language": "en"}' \
    "$HA_URL/api/conversation/process")

SPEECH=$(echo "$RESPONSE" | jq -r '.response.speech.plain.speech // "N/A"')
echo "[2c] Ollama response: $SPEECH"

# Wait for script to execute
sleep 2

# Check if last_triggered changed
AFTER_TRIGGERED=$(curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/states/script.get_pending_notification" | jq -r '.attributes.last_triggered // "never"')
echo "[2d] Script last_triggered after: $AFTER_TRIGGERED"
echo ""

if [[ "$BEFORE_TRIGGERED" != "$AFTER_TRIGGERED" ]]; then
    echo "RESULT: PASS - Ollama CAN call scripts"
    TOOL_CALLING="PASS"
else
    echo "RESULT: FAIL - Script was not called"
    TOOL_CALLING="FAIL"
fi

echo ""
echo "========================================================"
echo "  TEST 3: Check Ollama prompt/config"
echo "========================================================"
echo ""

# Get Ollama conversation agent info
echo "[3a] Checking conversation agent configuration..."
CONV_STATE=$(curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/states/conversation.ollama_conversation")
echo "Agent state: $(echo "$CONV_STATE" | jq -r '.state')"
echo "Supported features: $(echo "$CONV_STATE" | jq -r '.attributes.supported_features')"

# Check the prompt from storage (we found this earlier)
echo ""
echo "[3b] Current Ollama prompt (from earlier investigation):"
echo "     'You are a voice assistant for Home Assistant."
echo "      Answer questions about the world truthfully."
echo "      Answer in plain text. Keep it simple and to the point.'"
echo ""
echo "     NOTE: Prompt does NOT mention notifications or how to handle them"

echo ""
echo "========================================================"
echo "  DIAGNOSIS SUMMARY"
echo "========================================================"
echo ""
echo "State Reading:  $STATE_READING"
echo "Tool Calling:   $TOOL_CALLING"
echo ""

if [[ "$STATE_READING" == "PASS" && "$TOOL_CALLING" == "PASS" ]]; then
    echo "DIAGNOSIS: Both work! Issue is likely the PROMPT."
    echo "           Ollama doesn't know to call script for 'what is notification'"
    echo ""
    echo "RECOMMENDED FIX: Update Ollama prompt (Phase 2A)"
    echo "  Run: ./update-ollama-prompt.sh"
elif [[ "$STATE_READING" == "FAIL" ]]; then
    echo "DIAGNOSIS: State reading is broken (stale state bug confirmed)"
    echo ""
    echo "RECOMMENDED FIX: Switch to home-llm integration (Phase 2B)"
    echo "  Run: ./install-home-llm.sh"
elif [[ "$TOOL_CALLING" == "FAIL" ]]; then
    echo "DIAGNOSIS: Tool calling is broken"
    echo ""
    echo "RECOMMENDED FIX: Check llm_hass_api configuration and entity exposure"
fi

echo ""
echo "========================================================"
