#!/bin/bash
# Disable old/duplicate Claude automations, keep only v2
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

[[ -f "$ENV_FILE" ]] && HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
[[ -z "$HA_TOKEN" ]] && { echo "ERROR: HA_TOKEN not found"; exit 1; }

HA_HOST="${HA_HOST:-homeassistant.maas:8123}"

# Old automations to disable (replaced by v2)
OLD_AUTOMATIONS=(
    "automation.claude_code_led_feedback"
    "automation.claude_approval_dial_cw_approve"
    "automation.claude_approval_dial_ccw_reject"
    "automation.claude_approval_start_timer"
    "automation.claude_approval_timeout"
    "automation.claude_approval_cancel_timer"
    "automation.claude_approval_capture_request"
)

echo "=== Disabling old Claude automations ==="
echo ""

for automation in "${OLD_AUTOMATIONS[@]}"; do
    echo -n "Disabling $automation... "
    response=$(curl -s -X POST \
        -H "Authorization: Bearer $HA_TOKEN" \
        -H "Content-Type: application/json" \
        -d "{\"entity_id\": \"$automation\"}" \
        "http://$HA_HOST/api/services/automation/turn_off")

    if [[ -z "$response" || "$response" == "[]" ]]; then
        echo "OK (or already off)"
    else
        echo "Done"
    fi
done

echo ""
echo "=== Current Claude automations ==="
"$SCRIPT_DIR/../../haos/list-automations.sh" claude
