#!/bin/bash
# Acceptance test for Voice PE firmware upgrade
# Run after flashing new firmware to verify everything works
#
# Tests:
# 1. Device reachable (ping)
# 2. HA sees the device (entity check)
# 3. Satellite state is idle
# 4. LED ring controllable (on/off)
# 5. LED ring auto-off after voice interaction (the bug we're fixing)
# 6. Voice pipeline end-to-end
#
# Usage: test-firmware-upgrade.sh [--rollback-on-fail]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib-sh/ha-api.sh"

VOICE_PE_IP="192.168.86.10"
SAT_ENTITY="assist_satellite.home_assistant_voice_09f5a3_assist_satellite"
LED_ENTITY="light.home_assistant_voice_09f5a3_led_ring"
ROLLBACK="${1:-}"

PASSED=0
FAILED=0
TESTS=()

pass() { PASSED=$((PASSED + 1)); TESTS+=("PASS: $1"); echo "  PASS: $1"; }
fail() { FAILED=$((FAILED + 1)); TESTS+=("FAIL: $1"); echo "  FAIL: $1"; }

echo "=== Voice PE Firmware Upgrade Acceptance Test ==="
echo ""

# 1. Device reachable
echo "[1/6] Checking device reachability..."
if ping -c 2 -t 5 "$VOICE_PE_IP" >/dev/null 2>&1; then
    pass "Device reachable at $VOICE_PE_IP"
else
    fail "Device not reachable at $VOICE_PE_IP"
fi

# 2. HA sees the device
echo "[2/6] Checking HA entity..."
SAT_STATE=$(ha_get_state "$SAT_ENTITY" 2>/dev/null | jq -r '.state' 2>/dev/null)
if [[ -n "$SAT_STATE" && "$SAT_STATE" != "null" && "$SAT_STATE" != "unavailable" ]]; then
    pass "HA sees satellite (state: $SAT_STATE)"
else
    fail "HA cannot see satellite (state: $SAT_STATE)"
fi

# 3. Satellite idle
echo "[3/6] Checking satellite is idle..."
if [[ "$SAT_STATE" == "idle" ]]; then
    pass "Satellite is idle"
else
    fail "Satellite is not idle (state: $SAT_STATE)"
fi

# 4. LED ring controllable
echo "[4/6] Testing LED ring control..."
# Turn on blue
curl -s --fail-with-body --max-time 10 \
    -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    --data-raw "{\"entity_id\": \"$LED_ENTITY\", \"rgb_color\": [0, 0, 255], \"brightness\": 128}" \
    "$HA_URL/api/services/light/turn_on" >/dev/null 2>&1
sleep 1

LED_STATE=$(ha_get_state "$LED_ENTITY" 2>/dev/null | jq -r '.state' 2>/dev/null)
if [[ "$LED_STATE" == "on" ]]; then
    pass "LED ring turns on"
else
    fail "LED ring did not turn on (state: $LED_STATE)"
fi

# Turn off
curl -s --fail-with-body --max-time 10 \
    -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    --data-raw "{\"entity_id\": \"$LED_ENTITY\"}" \
    "$HA_URL/api/services/light/turn_off" >/dev/null 2>&1
sleep 1

LED_STATE=$(ha_get_state "$LED_ENTITY" 2>/dev/null | jq -r '.state' 2>/dev/null)
if [[ "$LED_STATE" == "off" ]]; then
    pass "LED ring turns off"
else
    fail "LED ring did not turn off (state: $LED_STATE)"
fi

# 5. LED auto-off after announce (the stuck-blue bug)
echo "[5/6] Testing LED auto-off after voice interaction (stuck-blue bug fix)..."
# Send an announce — this should cycle: idle → responding → idle
# and the LED should turn off automatically after
curl -s --fail-with-body --max-time 30 \
    -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    --data-raw "{\"entity_id\": \"$SAT_ENTITY\", \"message\": \"Firmware test\"}" \
    "$HA_URL/api/services/assist_satellite/announce" >/dev/null 2>&1

# Wait for announce to complete (TTS + playback)
sleep 8

SAT_STATE=$(ha_get_state "$SAT_ENTITY" 2>/dev/null | jq -r '.state' 2>/dev/null)
LED_STATE=$(ha_get_state "$LED_ENTITY" 2>/dev/null | jq -r '.state' 2>/dev/null)

if [[ "$SAT_STATE" == "idle" ]]; then
    pass "Satellite returned to idle after announce"
else
    fail "Satellite stuck in '$SAT_STATE' after announce"
fi

if [[ "$LED_STATE" == "off" ]]; then
    pass "LED ring auto-off after announce (bug fix verified!)"
else
    fail "LED ring stuck ON after announce (state: $LED_STATE) — bug NOT fixed"
fi

# 6. Voice pipeline check (Ollama integration)
echo "[6/6] Checking voice pipeline (Ollama integration)..."
OLLAMA_STATE=$(ha_api_get "config/config_entries/entry" 2>/dev/null | \
    jq -r '.[] | select(.domain == "ollama") | .state' | head -1)
if [[ "$OLLAMA_STATE" == "loaded" ]]; then
    pass "Ollama integration loaded"
else
    fail "Ollama integration not loaded (state: $OLLAMA_STATE)"
fi

# Summary
echo ""
echo "=== Results ==="
for t in "${TESTS[@]}"; do echo "  $t"; done
echo ""
echo "Passed: $PASSED  Failed: $FAILED"

if [[ $FAILED -gt 0 ]]; then
    echo ""
    echo "FIRMWARE UPGRADE FAILED ACCEPTANCE TESTS"
    if [[ "$ROLLBACK" == "--rollback-on-fail" ]]; then
        echo ""
        echo "To rollback, edit voice-pe-config.yaml to previous version,"
        echo "recompile, and USB flash again."
        echo "See: docs/runbooks/voice-pe-firmware-upgrade.md"
    fi
    exit 1
else
    echo ""
    echo "ALL TESTS PASSED — firmware upgrade successful"
fi
