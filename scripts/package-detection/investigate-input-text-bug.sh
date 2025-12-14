#!/bin/bash
# Investigate: Is input_text reading actually broken, or query misunderstanding?
# Goal: Get HARD EVIDENCE for root cause

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
echo "  INVESTIGATION: input_text State Reading"
echo "  Goal: Determine if bug or query misunderstanding"
echo "========================================================"
echo ""

# Record start time
START_TIME=$(date +"%H:%M")
echo "Investigation started at: $START_TIME"
echo ""

echo "========================================================"
echo "  TEST 1: Time Correlation"
echo "  If response ≈ current time → NOT a cache bug"
echo "========================================================"
echo ""

# Set a unique value
TEST_VALUE_1="TIMECORR-$(date +%s)"
echo "Setting input_text to: $TEST_VALUE_1"
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    -d "{\"entity_id\": \"input_text.pending_notification_message\", \"value\": \"$TEST_VALUE_1\"}" \
    "$HA_URL/api/services/input_text/set_value" > /dev/null

sleep 2

# Query and record time
QUERY_TIME_1=$(date +"%H:%M %p" | sed 's/AM/AM/;s/PM/PM/')
QUERY_TIME_1_ALT=$(date +"%l:%M %p" | sed 's/^ //')  # Alternative format without leading zero
echo "Query time (wall clock): $QUERY_TIME_1 (or $QUERY_TIME_1_ALT)"

RESPONSE_1=$(curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    -d '{"text": "what is the state of input_text.pending_notification_message", "language": "en"}' \
    "$HA_URL/api/conversation/process")

SPEECH_1=$(echo "$RESPONSE_1" | jq -r '.response.speech.plain.speech // "N/A"')
TYPE_1=$(echo "$RESPONSE_1" | jq -r '.response.response_type // "N/A"')

echo "Ollama response: $SPEECH_1"
echo "Response type: $TYPE_1"
echo ""

# Check if response looks like time
if echo "$SPEECH_1" | grep -qiE "^[0-9]{1,2}:[0-9]{2}|AM|PM|o.clock"; then
    echo "⚠️  Response appears to be a TIME, not entity value"
    echo "   This suggests Ollama is answering 'what time is it'"
else
    echo "   Response does not appear to be a time format"
fi

echo ""
echo "========================================================"
echo "  TEST 2: Stale Cache Check"
echo "  Set A, query, set B, query - see if returns stale A"
echo "========================================================"
echo ""

# Set to ALPHA
ALPHA_VALUE="ALPHA-$(date +%s)"
echo "Step 1: Setting to $ALPHA_VALUE"
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    -d "{\"entity_id\": \"input_text.pending_notification_message\", \"value\": \"$ALPHA_VALUE\"}" \
    "$HA_URL/api/services/input_text/set_value" > /dev/null
sleep 1

# Verify via API
ACTUAL_A=$(curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/states/input_text.pending_notification_message" | jq -r '.state')
echo "   API confirms: $ACTUAL_A"

# Query via conversation
echo "Step 2: Querying via conversation..."
RESPONSE_A=$(curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    -d '{"text": "what is input_text.pending_notification_message", "language": "en"}' \
    "$HA_URL/api/conversation/process")
SPEECH_A=$(echo "$RESPONSE_A" | jq -r '.response.speech.plain.speech // "N/A"')
echo "   Ollama says: $SPEECH_A"

# Set to BETA
BETA_VALUE="BETA-$(date +%s)"
echo ""
echo "Step 3: Setting to $BETA_VALUE"
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    -d "{\"entity_id\": \"input_text.pending_notification_message\", \"value\": \"$BETA_VALUE\"}" \
    "$HA_URL/api/services/input_text/set_value" > /dev/null
sleep 1

# Verify via API
ACTUAL_B=$(curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/states/input_text.pending_notification_message" | jq -r '.state')
echo "   API confirms: $ACTUAL_B"

# Query via conversation again
echo "Step 4: Querying via conversation again..."
RESPONSE_B=$(curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    -d '{"text": "what is input_text.pending_notification_message", "language": "en"}' \
    "$HA_URL/api/conversation/process")
SPEECH_B=$(echo "$RESPONSE_B" | jq -r '.response.speech.plain.speech // "N/A"')
echo "   Ollama says: $SPEECH_B"

echo ""
echo "Analysis:"
if [[ "$SPEECH_B" == *"$ALPHA_VALUE"* ]]; then
    echo "   ⚠️  STALE CACHE CONFIRMED: Returns ALPHA when value is BETA"
elif [[ "$SPEECH_A" == *"$ALPHA_VALUE"* ]] && [[ "$SPEECH_B" == *"$BETA_VALUE"* ]]; then
    echo "   ✓ State reading WORKS: Both queries returned correct values"
else
    echo "   ❌ Neither response contains entity values"
    echo "      This is NOT a stale cache bug - Ollama isn't reading entity at all"
fi

echo ""
echo "========================================================"
echo "  TEST 3: Response Structure Comparison"
echo "  Compare input_boolean (works) vs input_text (fails)"
echo "========================================================"
echo ""

# Ensure boolean is on
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    -d '{"entity_id": "input_boolean.has_pending_notification"}' \
    "$HA_URL/api/services/input_boolean/turn_on" > /dev/null
sleep 1

echo "Query: 'what is the state of has_pending_notification'"
BOOL_RESPONSE=$(curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    -d '{"text": "what is the state of has_pending_notification", "language": "en"}' \
    "$HA_URL/api/conversation/process")

echo "Full response (input_boolean):"
echo "$BOOL_RESPONSE" | jq '{response_type: .response.response_type, speech: .response.speech.plain.speech, data: .response.data}'

echo ""
echo "Query: 'what is the state of pending_notification_message'"
TEXT_RESPONSE=$(curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    -d '{"text": "what is the state of pending_notification_message", "language": "en"}' \
    "$HA_URL/api/conversation/process")

echo "Full response (input_text):"
echo "$TEXT_RESPONSE" | jq '{response_type: .response.response_type, speech: .response.speech.plain.speech, data: .response.data}'

echo ""
BOOL_TYPE=$(echo "$BOOL_RESPONSE" | jq -r '.response.response_type')
TEXT_TYPE=$(echo "$TEXT_RESPONSE" | jq -r '.response.response_type')

echo "Comparison:"
echo "   input_boolean response_type: $BOOL_TYPE"
echo "   input_text response_type: $TEXT_TYPE"

if [[ "$BOOL_TYPE" == "query_answer" ]] && [[ "$TEXT_TYPE" != "query_answer" ]]; then
    echo "   ⚠️  Different response types - input_text not recognized as state query"
fi

echo ""
echo "========================================================"
echo "  CONCLUSION"
echo "========================================================"
echo ""

# Summarize findings
echo "Evidence collected:"
echo ""
echo "Test 1 (Time Correlation):"
echo "   Query time: $QUERY_TIME_1"
echo "   Response: $SPEECH_1"
if echo "$SPEECH_1" | grep -qiE "^[0-9]{1,2}:[0-9]{2}|AM|PM"; then
    echo "   → Response IS current time - Ollama answering conversationally"
fi

echo ""
echo "Test 2 (Stale Cache):"
echo "   ALPHA value: $ALPHA_VALUE"
echo "   Response when ALPHA: $SPEECH_A"
echo "   BETA value: $BETA_VALUE"
echo "   Response when BETA: $SPEECH_B"

echo ""
echo "Test 3 (Response Types):"
echo "   input_boolean: $BOOL_TYPE"
echo "   input_text: $TEXT_TYPE"

echo ""
echo "========================================================"
