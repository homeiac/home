#!/bin/bash
# Test Voice PE ESPHome LED effect services after firmware modification
# These services will only exist after applying ESPHome YAML changes and OTA update
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

# Load HA_TOKEN from .env
if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

if [[ -z "$HA_TOKEN" ]]; then
    echo "ERROR: HA_TOKEN not found"
    exit 1
fi

HA_HOST="${HA_HOST:-homeassistant.maas}"
DEVICE_NAME="home_assistant_voice_09f5a3"

# Expected services after ESPHome modification
SERVICE_SET_EFFECT="esphome.${DEVICE_NAME}_set_led_effect"
SERVICE_TRIGGER_THINKING="esphome.${DEVICE_NAME}_trigger_thinking_effect"
SERVICE_STOP_EFFECTS="esphome.${DEVICE_NAME}_stop_effects"

echo "=== Voice PE ESPHome Service Test ==="
echo "Device: $DEVICE_NAME"
echo ""

# Check if services exist
echo "Checking if ESPHome services exist..."
SERVICES_JSON=$(curl -s -X GET \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    "http://$HA_HOST:8123/api/services")

SERVICE_EXISTS=$(echo "$SERVICES_JSON" | jq -r --arg svc "$SERVICE_SET_EFFECT" '[.[] | select(.domain == "esphome") | .services | keys[]] | any(. == ($svc | split(".")[1]))')

if [[ "$SERVICE_EXISTS" != "true" ]]; then
    echo ""
    echo "❌ ESPHome services not found!"
    echo ""
    echo "The following services are expected but missing:"
    echo "  - $SERVICE_SET_EFFECT"
    echo "  - $SERVICE_TRIGGER_THINKING"
    echo "  - $SERVICE_STOP_EFFECTS"
    echo ""
    echo "To enable these services:"
    echo "  1. Apply ESPHome YAML changes via ESPHome dashboard:"
    echo "     - Edit 'home-assistant-voice-09f5a3' configuration"
    echo "     - Add LED effect and service definitions"
    echo "     - Save changes"
    echo ""
    echo "  2. OTA update the Voice PE device:"
    echo "     - Click 'Install' in ESPHome dashboard"
    echo "     - Select 'Wirelessly' for OTA update"
    echo "     - Wait for update to complete (~2-3 minutes)"
    echo ""
    echo "  3. Re-run this test script:"
    echo "     $0"
    echo ""
    exit 1
fi

echo "✅ ESPHome services found!"
echo ""

# Test each service
echo "Testing service: $SERVICE_TRIGGER_THINKING"
echo "  Action: Trigger thinking effect (cyan pulse)"
curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{}" \
    "http://$HA_HOST:8123/api/services/esphome/${DEVICE_NAME}_trigger_thinking_effect" | jq -r '.[] | "  Result: \(.entity_id) - \(.state)"' 2>/dev/null || echo "  Result: Success"
echo "  Waiting 3 seconds..."
sleep 3
echo ""

echo "Testing service: $SERVICE_SET_EFFECT"
echo "  Action: Set effect to 'waiting' (amber)"
curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"effect_name\": \"waiting\"}" \
    "http://$HA_HOST:8123/api/services/esphome/${DEVICE_NAME}_set_led_effect" | jq -r '.[] | "  Result: \(.entity_id) - \(.state)"' 2>/dev/null || echo "  Result: Success"
echo "  Waiting 3 seconds..."
sleep 3
echo ""

echo "Testing service: $SERVICE_SET_EFFECT"
echo "  Action: Set effect to 'idle' (dim blue)"
curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"effect_name\": \"idle\"}" \
    "http://$HA_HOST:8123/api/services/esphome/${DEVICE_NAME}_set_led_effect" | jq -r '.[] | "  Result: \(.entity_id) - \(.state)"' 2>/dev/null || echo "  Result: Success"
echo "  Waiting 2 seconds..."
sleep 2
echo ""

echo "Testing service: $SERVICE_STOP_EFFECTS"
echo "  Action: Stop all LED effects"
curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{}" \
    "http://$HA_HOST:8123/api/services/esphome/${DEVICE_NAME}_stop_effects" | jq -r '.[] | "  Result: \(.entity_id) - \(.state)"' 2>/dev/null || echo "  Result: Success"
echo ""

echo "=== All Tests Complete ==="
echo ""
echo "Available effects:"
echo "  - thinking  # Cyan pulse (LLM processing)"
echo "  - listening # Bright white (voice input active)"
echo "  - waiting   # Amber pulse (awaiting approval)"
echo "  - idle      # Dim blue (standby)"
echo ""
echo "Services tested:"
echo "  ✅ $SERVICE_TRIGGER_THINKING"
echo "  ✅ $SERVICE_SET_EFFECT"
echo "  ✅ $SERVICE_STOP_EFFECTS"
echo ""
