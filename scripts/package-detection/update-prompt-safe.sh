#!/bin/bash
# Safe prompt update using jq directly in VM

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

# Escaped prompt for jq (single quotes, newlines as \n)
NEW_PROMPT='You are a voice assistant for Home Assistant.\n\nIMPORTANT - Notification handling:\nWhen the user asks about notifications (e.g., "what is the notification", "check my notifications", "any notifications", "what are my alerts"):\n1. Call script.get_pending_notification - it will announce the message and clear the notification\n2. Do NOT try to read input_text.pending_notification_message directly\n\nFor all other requests:\n- Answer questions truthfully\n- Keep responses simple and to the point\n- Use plain text'

STORAGE_FILE="/mnt/data/supervisor/homeassistant/.storage/core.config_entries"

echo "========================================================"
echo "  Safe Prompt Update Using In-VM jq"
echo "========================================================"
echo ""

echo "1. Checking if jq is available in VM..."
JQ_CHECK=$(timeout 30 ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null root@chief-horse.maas \
    "qm guest exec 116 -- which jq 2>/dev/null" 2>/dev/null | jq -r '."out-data" // "NOT FOUND"')
echo "   jq location: $JQ_CHECK"

if [[ "$JQ_CHECK" == "NOT FOUND" ]] || [[ -z "$JQ_CHECK" ]]; then
    echo ""
    echo "   jq not found in VM. Trying to install..."
    timeout 60 ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null root@chief-horse.maas \
        "qm guest exec 116 -- apk add jq 2>/dev/null" 2>/dev/null || echo "   Could not install jq"
fi

echo ""
echo "2. Creating backup in VM..."
timeout 30 ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null root@chief-horse.maas \
    "qm guest exec 116 -- cp $STORAGE_FILE ${STORAGE_FILE}.backup.$(date +%Y%m%d_%H%M%S) 2>/dev/null" 2>/dev/null

echo ""
echo "3. Current prompt before update..."
timeout 30 ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null root@chief-horse.maas \
    "qm guest exec 116 -- cat $STORAGE_FILE 2>/dev/null" 2>/dev/null | \
    jq -r '."out-data" // .' 2>/dev/null | \
    jq -r '.data.entries[] | select(.domain == "ollama") | .subentries[0].data.prompt' 2>/dev/null | head -3
echo "   ..."

echo ""
echo "4. Updating prompt using jq in VM..."
# Create a script to run inside the VM
UPDATE_SCRIPT='
STORAGE_FILE="/mnt/data/supervisor/homeassistant/.storage/core.config_entries"
NEW_PROMPT="You are a voice assistant for Home Assistant.

IMPORTANT - Notification handling:
When the user asks about notifications (e.g., \"what is the notification\", \"check my notifications\", \"any notifications\", \"what are my alerts\"):
1. Call script.get_pending_notification - it will announce the message and clear the notification
2. Do NOT try to read input_text.pending_notification_message directly

For all other requests:
- Answer questions truthfully
- Keep responses simple and to the point
- Use plain text"

jq --arg prompt "$NEW_PROMPT" '\''
    .data.entries |= map(
        if .domain == "ollama" then
            .subentries[0].data.prompt = $prompt
        else
            .
        end
    )
'\'' "$STORAGE_FILE" > /tmp/config_updated.json && mv /tmp/config_updated.json "$STORAGE_FILE"
'

# Write the script to Proxmox host first
echo "$UPDATE_SCRIPT" > /tmp/update_prompt_in_vm.sh

# Copy to Proxmox host
scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null /tmp/update_prompt_in_vm.sh root@chief-horse.maas:/tmp/

# Execute via qm guest exec with input-data
timeout 60 ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null root@chief-horse.maas \
    "cat /tmp/update_prompt_in_vm.sh | qm guest exec 116 --pass-stdin -- sh"

echo ""
echo "5. Verifying update..."
timeout 30 ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null root@chief-horse.maas \
    "qm guest exec 116 -- cat $STORAGE_FILE 2>/dev/null" 2>/dev/null | \
    jq -r '."out-data" // .' 2>/dev/null | \
    jq -r '.data.entries[] | select(.domain == "ollama") | .subentries[0].data.prompt' 2>/dev/null | head -5

echo ""
echo "6. Checking file size..."
timeout 30 ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null root@chief-horse.maas \
    "qm guest exec 116 -- ls -la $STORAGE_FILE 2>/dev/null" 2>/dev/null | \
    jq -r '."out-data" // .'

echo ""
echo "7. Restarting Home Assistant..."
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/services/homeassistant/restart" > /dev/null

echo "   Waiting for HA to come back..."
for i in {1..60}; do
    sleep 5
    if curl -s --max-time 5 -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/" > /dev/null 2>&1; then
        echo "   HA is back online after ~$((i * 5)) seconds"
        break
    fi
    echo "   Still waiting... ($i/60)"
done

sleep 10
echo ""
echo "8. Testing prompt effect..."
echo "   Setting test notification..."
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    -d '{"entity_id": "input_text.pending_notification_message", "value": "TEST-PROMPT-UPDATE"}' \
    "$HA_URL/api/services/input_text/set_value" > /dev/null
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    -d '{"entity_id": "input_boolean.has_pending_notification"}' \
    "$HA_URL/api/services/input_boolean/turn_on" > /dev/null

echo "   Testing 'what is the notification'..."
RESPONSE=$(curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    -d '{"text": "what is the notification", "language": "en"}' \
    "$HA_URL/api/conversation/process")
echo "   Response: $(echo "$RESPONSE" | jq -r '.response.speech.plain.speech // "N/A"')"
echo "   Type: $(echo "$RESPONSE" | jq -r '.response.response_type // "N/A"')"

echo ""
echo "========================================================"
