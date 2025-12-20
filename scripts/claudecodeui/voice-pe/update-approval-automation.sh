#!/bin/bash
# Update approval-request automation to use assist_satellite.start_conversation
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HA_CONFIG="/mnt/data/supervisor/homeassistant"
PROXMOX_HOST="root@chief-horse.maas"
VMID=116

ha_exec() {
    ssh "$PROXMOX_HOST" "qm guest exec $VMID -- $*" 2>/dev/null | jq -r '.["out-data"] // .exitcode'
}

echo "=== Checking current approval-request automation ==="

# Get current automation
ssh "$PROXMOX_HOST" "qm guest exec $VMID -- cat $HA_CONFIG/automations.yaml" 2>/dev/null | \
    jq -r '.["out-data"]' > /tmp/ha-automations.yaml

# Check if tts.speak is used (current method)
if grep -q "tts.speak" /tmp/ha-automations.yaml; then
    echo "Found tts.speak in automation - this needs to change to assist_satellite.start_conversation"
    echo ""

    # Show current TTS section
    echo "Current TTS call:"
    grep -A5 "tts.speak" /tmp/ha-automations.yaml | head -10
    echo ""

    echo "Need to replace with:"
    echo "  - action: assist_satellite.start_conversation"
    echo "    target:"
    echo "      entity_id: assist_satellite.home_assistant_voice_09f5a3_assist_satellite"
    echo "    data:"
    echo '      start_message: "{{ trigger.payload_json.message }}"'
    echo ""
    echo "This change requires manual edit in HA UI or file edit."
    echo ""
    echo "Steps:"
    echo "1. Go to HA Settings > Automations"
    echo "2. Find 'Claude Code LED Feedback' automation"
    echo "3. In approval_request action, replace tts.speak with assist_satellite.start_conversation"
    echo "4. Save and test"
else
    echo "No tts.speak found - checking for assist_satellite..."
    if grep -q "assist_satellite.start_conversation" /tmp/ha-automations.yaml; then
        echo "Already using assist_satellite.start_conversation!"
    else
        echo "Neither found - automation may need review"
    fi
fi
