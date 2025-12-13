#!/bin/bash
# Check entity exposure for conversation in HA storage

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "========================================================"
echo "  Check Entity Exposure for Conversation"
echo "========================================================"
echo ""

echo "1. Checking entity registry for conversation exposure..."
timeout 30 ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null root@chief-horse.maas \
    "qm guest exec 116 -- cat /mnt/data/supervisor/homeassistant/.storage/core.entity_registry 2>/dev/null" 2>/dev/null | \
    jq -r '."out-data" // .' 2>/dev/null | \
    jq '.data.entities[] | select(.entity_id | test("notification|pending|get_pending")) | {entity_id, options}' 2>/dev/null

echo ""
echo "2. Count of entities exposed to conversation..."
EXPOSED=$(timeout 30 ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null root@chief-horse.maas \
    "qm guest exec 116 -- cat /mnt/data/supervisor/homeassistant/.storage/core.entity_registry 2>/dev/null" 2>/dev/null | \
    jq -r '."out-data" // .' 2>/dev/null | \
    jq '[.data.entities[] | select(.options.conversation.should_expose == true)] | length' 2>/dev/null)
echo "   Total entities exposed: $EXPOSED"

echo ""
echo "3. List ALL entities exposed to conversation..."
timeout 30 ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null root@chief-horse.maas \
    "qm guest exec 116 -- cat /mnt/data/supervisor/homeassistant/.storage/core.entity_registry 2>/dev/null" 2>/dev/null | \
    jq -r '."out-data" // .' 2>/dev/null | \
    jq '.data.entities[] | select(.options.conversation.should_expose == true) | .entity_id' 2>/dev/null | head -20

echo ""
echo "========================================================"
echo "  Diagnosis"
echo "========================================================"

if [[ "$EXPOSED" == "0" ]] || [[ -z "$EXPOSED" ]]; then
    echo ""
    echo "NO ENTITIES ARE EXPOSED TO CONVERSATION!"
    echo ""
    echo "This is why tool calling doesn't work. Even though llm_hass_api=assist"
    echo "is configured, Ollama has no entities to control."
    echo ""
    echo "FIX: Expose entities in Settings → Voice assistants → Expose tab"
    echo "     Or via Settings → Devices → Entity → 'Expose to Assist'"
else
    echo ""
    echo "$EXPOSED entities are exposed. Let me check which notification entities..."
fi

echo ""
echo "========================================================"
