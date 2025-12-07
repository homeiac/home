#!/bin/bash
# Package Detection Prerequisites Check
# Reads HA_TOKEN from .env file - never hardcode tokens

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../../proxmox/homelab/.env"

# Load HA_TOKEN from .env
if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2)
else
    echo "ERROR: .env file not found at $ENV_FILE"
    exit 1
fi

if [[ -z "$HA_TOKEN" ]]; then
    echo "ERROR: HA_TOKEN not found in .env"
    exit 1
fi

HA_URL="http://192.168.4.240:8123"
OLLAMA_URL="http://192.168.4.81"

echo "=== Package Detection Prerequisites Check ==="
echo ""

# 1. Check HA API
echo "1. Home Assistant API..."
HA_STATUS=$(curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/" 2>/dev/null)
if echo "$HA_STATUS" | grep -q "API running"; then
    echo "   ✅ HA API is accessible"
else
    echo "   ❌ HA API failed: $HA_STATUS"
    exit 1
fi

# 2. Check notify services
echo ""
echo "2. Notification Services..."
NOTIFY_SERVICES=$(curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/services" 2>/dev/null | \
    python3 -c "import sys,json; d=json.load(sys.stdin); [print('   - notify.' + k) for s in d if s['domain']=='notify' for k in s['services'].keys()]" 2>/dev/null || echo "   Failed to parse")
if [[ -n "$NOTIFY_SERVICES" ]]; then
    echo "$NOTIFY_SERVICES"
else
    echo "   ❌ No notify services found"
fi

# 3. Check Voice PE entities
echo ""
echo "3. Voice PE Entities..."
curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/states" 2>/dev/null | \
    python3 -c "import sys,json; d=json.load(sys.stdin); [print('   - ' + e['entity_id']) for e in d if 'voice' in e['entity_id'].lower() or 'assist_satellite' in e['entity_id']]" 2>/dev/null || echo "   Failed to parse"

# 4. Check Frigate entities
echo ""
echo "4. Frigate Camera Entities..."
curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/states" 2>/dev/null | \
    python3 -c "import sys,json; d=json.load(sys.stdin); [print('   - ' + e['entity_id']) for e in d if 'frigate' in e['entity_id'].lower() and 'camera' in e['entity_id']]" 2>/dev/null || echo "   Failed to parse"

# 5. Check Ollama
echo ""
echo "5. Ollama Models..."
OLLAMA_MODELS=$(curl -s "$OLLAMA_URL/api/tags" 2>/dev/null | \
    python3 -c "import sys,json; d=json.load(sys.stdin); [print('   - ' + m['name']) for m in d.get('models',[])]" 2>/dev/null)
if [[ -n "$OLLAMA_MODELS" ]]; then
    echo "$OLLAMA_MODELS"

    # Check for vision model
    if echo "$OLLAMA_MODELS" | grep -qiE "llava|moondream|bakllava|vision"; then
        echo "   ✅ Vision model available"
    else
        echo "   ⚠️  No vision model found - will need to pull one (llava or moondream)"
    fi
else
    echo "   ❌ Ollama not accessible at $OLLAMA_URL"
fi

# 6. Check LLM Vision integration
echo ""
echo "6. LLM Vision Integration..."
LLM_VISION=$(curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/services" 2>/dev/null | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print('found' if any(s['domain']=='llmvision' for s in d) else 'not_found')" 2>/dev/null)
if [[ "$LLM_VISION" == "found" ]]; then
    echo "   ✅ LLM Vision integration installed"
else
    echo "   ❌ LLM Vision integration not found"
fi

echo ""
echo "=== Prerequisites Check Complete ==="
