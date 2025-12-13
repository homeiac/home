#!/bin/bash
# Comprehensive Package Detection Investigation Script
# Usage: ./investigate-package-detection.sh
#
# This script checks ALL components of the package detection system
# to identify exactly where the failure is occurring.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../../proxmox/homelab/.env"

HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2)
HA_URL="http://192.168.4.240:8123"

echo "=============================================="
echo "PACKAGE DETECTION INVESTIGATION"
echo "=============================================="
echo ""

# ============================================
# PHASE 0: Verify All Components Exist
# ============================================
echo "=== PHASE 0: COMPONENT VERIFICATION ==="
echo ""

# Check 1: Automation exists and is enabled
echo "--- Check 1: Automation Status ---"
AUTOMATION_STATE=$(curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/states" | \
    jq -r '.[] | select(.entity_id | contains("package_delivery_detection")) | "\(.entity_id): \(.state)"')

if [ -z "$AUTOMATION_STATE" ]; then
    echo "❌ CRITICAL: automation.package_delivery_detection NOT FOUND"
    echo "   The automation is not deployed to Home Assistant!"
    echo "   Run: ./deploy-automation-v2.sh"
else
    echo "✅ Automation found: $AUTOMATION_STATE"
fi
echo ""

# Check 2: Helper entities
echo "--- Check 2: Helper Entities ---"
HELPERS=(
    "input_text.pending_notification_message"
    "input_text.pending_notification_type"
    "input_boolean.has_pending_notification"
)
for helper in "${HELPERS[@]}"; do
    STATE=$(curl -s -H "Authorization: Bearer $HA_TOKEN" \
        "$HA_URL/api/states/$helper" | jq -r '.state // "NOT_FOUND"')
    if [ "$STATE" = "NOT_FOUND" ] || [ -z "$STATE" ]; then
        echo "❌ MISSING: $helper"
    else
        echo "✅ $helper = \"$STATE\""
    fi
done
echo ""

# Check 3: LED Entity
echo "--- Check 3: LED Entity ---"
LED_DATA=$(curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/states/light.home_assistant_voice_09f5a3_led_ring")
LED_STATE=$(echo "$LED_DATA" | jq -r '.state // "NOT_FOUND"')
LED_BRIGHTNESS=$(echo "$LED_DATA" | jq -r '.attributes.brightness // "N/A"')
LED_RGB=$(echo "$LED_DATA" | jq -r '.attributes.rgb_color // "N/A"')

if [ "$LED_STATE" = "NOT_FOUND" ]; then
    echo "❌ CRITICAL: LED entity NOT FOUND"
    echo "   Voice PE device may be offline or not configured"
else
    echo "✅ LED Entity: state=$LED_STATE, brightness=$LED_BRIGHTNESS, rgb=$LED_RGB"
fi
echo ""

# Check 4: Reolink Person Sensor
echo "--- Check 4: Reolink Person Sensor ---"
SENSOR_DATA=$(curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/states/binary_sensor.reolink_video_doorbell_wifi_person")
SENSOR_STATE=$(echo "$SENSOR_DATA" | jq -r '.state // "NOT_FOUND"')
SENSOR_CHANGED=$(echo "$SENSOR_DATA" | jq -r '.last_changed // "never"')

if [ "$SENSOR_STATE" = "NOT_FOUND" ]; then
    echo "❌ CRITICAL: Reolink person sensor NOT FOUND"
else
    echo "✅ Person sensor: state=$SENSOR_STATE, last_changed=$SENSOR_CHANGED"
fi
echo ""

# Check 5: Camera Entity
echo "--- Check 5: Camera Entity ---"
CAMERA_STATE=$(curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/states/camera.reolink_video_doorbell_wifi_fluent" | jq -r '.state // "NOT_FOUND"')
if [ "$CAMERA_STATE" = "NOT_FOUND" ]; then
    echo "❌ CRITICAL: Camera entity NOT FOUND"
else
    echo "✅ Camera entity: state=$CAMERA_STATE"
fi
echo ""

# Check 6: LLM Vision Integration
echo "--- Check 6: LLM Vision Integration ---"
LLMVISION=$(curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/services" | jq -r '.[] | select(.domain == "llmvision") | .domain')
if [ -z "$LLMVISION" ]; then
    echo "❌ CRITICAL: LLM Vision service NOT FOUND"
else
    echo "✅ LLM Vision service available"
fi
echo ""

# ============================================
# PHASE 1: Check Recent Execution History
# ============================================
echo "=== PHASE 1: EXECUTION HISTORY ==="
echo ""

# Check automation traces
echo "--- Automation Traces (last 5) ---"
TRACES=$(curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/trace/automation.package_delivery_detection" 2>/dev/null)

if [ "$TRACES" = "[]" ] || [ -z "$TRACES" ] || echo "$TRACES" | grep -q "not found"; then
    echo "❌ No traces found - automation may never have run"
else
    echo "$TRACES" | jq -r '.[0:5] | .[] | "Run: \(.run_id) | Trigger: \(.trigger // "unknown") | State: \(.state)"' 2>/dev/null || echo "Unable to parse traces"
fi
echo ""

# Check recent person sensor history (last hour)
echo "--- Person Sensor Activity (last hour) ---"
ONE_HOUR_AGO=$(date -u -v-1H +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date -u -d '1 hour ago' +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null)
HISTORY=$(curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/history/period/$ONE_HOUR_AGO?filter_entity_id=binary_sensor.reolink_video_doorbell_wifi_person" 2>/dev/null)

if [ "$HISTORY" = "[[]]" ] || [ -z "$HISTORY" ]; then
    echo "No person sensor events in last hour"
else
    echo "$HISTORY" | jq -r '.[][] | "\(.last_changed): \(.state)"' 2>/dev/null | tail -10 || echo "Unable to parse history"
fi
echo ""

# Check LED history
echo "--- LED State History (last hour) ---"
LED_HISTORY=$(curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/history/period/$ONE_HOUR_AGO?filter_entity_id=light.home_assistant_voice_09f5a3_led_ring" 2>/dev/null)

if [ "$LED_HISTORY" = "[[]]" ] || [ -z "$LED_HISTORY" ]; then
    echo "No LED state changes in last hour"
else
    echo "$LED_HISTORY" | jq -r '.[][] | "\(.last_changed): \(.state)"' 2>/dev/null | tail -10 || echo "Unable to parse LED history"
fi
echo ""

# ============================================
# PHASE 2: Test Individual Components
# ============================================
echo "=== PHASE 2: COMPONENT TESTS ==="
echo ""

# Test LED control
echo "--- Test: LED Control ---"
echo "Turning LED blue for 3 seconds..."
curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"entity_id": "light.home_assistant_voice_09f5a3_led_ring", "rgb_color": [0, 100, 255], "brightness": 200}' \
    "$HA_URL/api/services/light/turn_on" > /dev/null

sleep 3

LED_AFTER=$(curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/states/light.home_assistant_voice_09f5a3_led_ring" | jq -r '.state')
echo "LED state after turn_on: $LED_AFTER"

curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"entity_id": "light.home_assistant_voice_09f5a3_led_ring"}' \
    "$HA_URL/api/services/light/turn_off" > /dev/null

if [ "$LED_AFTER" = "on" ]; then
    echo "✅ LED control works - DID YOU SEE IT TURN BLUE?"
else
    echo "❌ LED failed to turn on (state=$LED_AFTER)"
fi
echo ""

# ============================================
# SUMMARY
# ============================================
echo "=============================================="
echo "INVESTIGATION SUMMARY"
echo "=============================================="
echo ""
echo "Key Questions to Answer:"
echo "1. Did automation.package_delivery_detection appear in the list? (If not, deploy it)"
echo "2. Did the LED turn blue during the test? (If not, hardware/network issue)"
echo "3. Are there any automation traces? (If not, automation never triggered)"
echo "4. Did person sensor show recent activity? (If not, sensor may not be triggering)"
echo ""
echo "Next Steps:"
echo "- If automation missing: ./deploy-automation-v2.sh"
echo "- If LED didn't work: Check Voice PE device in HA"
echo "- If no traces: Trigger person sensor and watch HA logs"
echo "- If traces exist: Read them to see where logic fails"
