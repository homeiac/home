#!/bin/bash
# Deep diagnosis of why Ollama tool calling isn't working

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
echo "  Deep Diagnosis: Why Tool Calling Fails"
echo "========================================================"
echo ""

echo "1. Check Ollama integration config entry..."
curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/config/config_entries/entry" | \
    jq '.[] | select(.domain == "ollama")' 2>/dev/null

echo ""
echo "2. Check llm_hass_api setting specifically..."
curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/config/config_entries/entry" | \
    jq '.[] | select(.domain == "ollama") | .options.llm_hass_api // "NOT SET"' 2>/dev/null

echo ""
echo "3. List ALL conversation agents and their capabilities..."
curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/states" | \
    jq '.[] | select(.entity_id | startswith("conversation.")) | {entity_id, state, friendly_name: .attributes.friendly_name, supported_features: .attributes.supported_features}' 2>/dev/null

echo ""
echo "4. Check what entities are exposed to conversation..."
EXPOSED_COUNT=$(curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/config/entity_registry/list" 2>/dev/null | \
    jq '[.[] | select(.options.conversation.should_expose == true)] | length' 2>/dev/null || echo "0")
echo "   Total entities exposed: $EXPOSED_COUNT"

echo ""
echo "5. Check if notification entities are specifically exposed..."
for entity in "input_boolean.has_pending_notification" "input_text.pending_notification_message" "script.get_pending_notification"; do
    EXPOSED=$(curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/config/entity_registry/list" 2>/dev/null | \
        jq -r --arg e "$entity" '.[] | select(.entity_id == $e) | .options.conversation.should_expose // "false"' 2>/dev/null || echo "unknown")
    echo "   $entity: exposed=$EXPOSED"
done

echo ""
echo "6. Test with explicit service call command..."
echo "   Asking: 'turn on input_boolean.has_pending_notification'"
RESPONSE=$(curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    -d '{"text": "turn on input_boolean.has_pending_notification", "language": "en"}' \
    "$HA_URL/api/conversation/process" 2>/dev/null)
echo "   Response: $(echo "$RESPONSE" | jq -r '.response.speech.plain.speech // "N/A"')"
echo "   Response type: $(echo "$RESPONSE" | jq -r '.response.response_type // "N/A"')"

echo ""
echo "7. Check conversation agent debug info..."
echo "   Full response structure:"
echo "$RESPONSE" | jq '.' 2>/dev/null | head -30

echo ""
echo "========================================================"
echo "  Analysis"
echo "========================================================"
echo ""

LLM_API=$(curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/config/config_entries/entry" | \
    jq -r '.[] | select(.domain == "ollama") | .options.llm_hass_api // ["none"] | .[0]' 2>/dev/null)

if [[ "$LLM_API" == "assist" ]]; then
    echo "llm_hass_api is set to 'assist' - tool calling SHOULD work"
    echo ""
    echo "Possible issues:"
    echo "  1. Model doesn't support function calling (qwen2.5:7b should)"
    echo "  2. Entities not properly exposed"
    echo "  3. Bug in native Ollama integration"
elif [[ "$LLM_API" == "none" ]] || [[ -z "$LLM_API" ]]; then
    echo "llm_hass_api is NOT SET or set to 'none'"
    echo ""
    echo "FIX REQUIRED: Enable 'Control Home Assistant' in Ollama integration"
    echo "  1. Go to Settings → Devices & Services → Ollama"
    echo "  2. Click Configure"
    echo "  3. Set 'LLM API' to 'Assist'"
else
    echo "llm_hass_api is set to: $LLM_API"
fi

echo ""
echo "========================================================"
