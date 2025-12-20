#!/bin/bash
# Check the status of the Claude Code LED automation
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

# Load HA_TOKEN from .env
if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

if [[ -z "$HA_TOKEN" ]]; then
    echo "ERROR: HA_TOKEN not found in $ENV_FILE"
    exit 1
fi

HA_HOST="${HA_HOST:-homeassistant.maas}"
AUTOMATION_ID="automation.claude_code_led_feedback"

echo "=== Claude Code LED Automation Status ==="
echo ""

# Get automation state
echo "Automation State:"
curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "http://$HA_HOST:8123/api/states/$AUTOMATION_ID" | \
    jq '{
        entity_id,
        state,
        last_triggered: .attributes.last_triggered,
        friendly_name: .attributes.friendly_name
    }'

echo ""
echo "=== Recent Automation Traces ==="

# Get traces (HA trace API uses different endpoint format)
TRACES=$(curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "http://$HA_HOST:8123/api/trace/automation/$AUTOMATION_ID" 2>/dev/null)

if echo "$TRACES" | jq -e 'type == "array"' >/dev/null 2>&1; then
    echo "$TRACES" | jq -r '
        if length > 0 then
            .[-5:] | .[] | "Run ID: \(.run_id // "n/a") | State: \(.state // "n/a") | Started: \(.timestamp // .last_step // "n/a")"
        else
            "No traces found"
        end
    '
else
    echo "Traces not available (API returned non-array)"
fi

echo ""
echo "=== LED Entity State ==="
curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "http://$HA_HOST:8123/api/states/light.home_assistant_voice_09f5a3_led_ring" | \
    jq '{entity_id, state, brightness: .attributes.brightness, rgb_color: .attributes.rgb_color}'
