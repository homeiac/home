#!/bin/bash
# Test LLM Vision package detection with current doorbell snapshot
# This can be run anytime to verify the LLM Vision pipeline works

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../../proxmox/homelab/.env"

HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2)
HA_URL="http://192.168.4.240:8123"

# LLM Vision provider entry_id for Ollama
OLLAMA_PROVIDER="01K1KDVH6Y1GMJ69MJF77WGJEA"

# Camera/image entity to test
IMAGE_ENTITY="${1:-image.reolink_doorbell_person}"

# Package detection prompt
PROMPT="Analyze this doorbell camera image. Answer ONLY YES or NO: Is there a package, box, parcel, or delivery item visible on the porch, at the door, or being held by a person? Do not consider people, vehicles, bags, or pets as packages."

echo "=== Testing LLM Vision Package Detection ==="
echo "Image entity: $IMAGE_ENTITY"
echo "Provider: Ollama (llava:7b)"
echo ""

# Check if the image entity has a recent snapshot
echo "Checking image entity state..."
IMAGE_STATE=$(curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/states/$IMAGE_ENTITY" 2>/dev/null)

LAST_UPDATED=$(echo "$IMAGE_STATE" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('last_updated', 'unknown'))
except:
    print('error')
" 2>/dev/null)
echo "Last updated: $LAST_UPDATED"
echo ""

echo "Calling LLM Vision (this may take 10-30 seconds)..."
echo ""

# Use action endpoint with return_response
RESPONSE=$(curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{
        \"provider\": \"$OLLAMA_PROVIDER\",
        \"model\": \"llava:7b\",
        \"image_entity\": [\"$IMAGE_ENTITY\"],
        \"message\": \"$PROMPT\",
        \"max_tokens\": 100,
        \"target_width\": 1280
    }" \
    "$HA_URL/api/services/llmvision/image_analyzer?return_response=true" 2>&1)

echo "=== Response ==="
echo "$RESPONSE" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    if isinstance(d, dict):
        # Check for service_response key (HA 2024.1+)
        if 'service_response' in d:
            resp = d['service_response']
            text = resp.get('response_text', resp.get('text', str(resp)))
            print(f'LLM says: {text}')
            if 'yes' in text.lower():
                print()
                print('✅ PACKAGE DETECTED - notification would be sent')
            else:
                print()
                print('❌ No package detected - no notification')
        elif 'response_text' in d:
            print(f'LLM says: {d[\"response_text\"]}')
        else:
            print(f'Response: {json.dumps(d, indent=2)}')
    elif isinstance(d, list) and len(d) == 0:
        print('Service called successfully but no response returned.')
        print('Note: In automations, use response_variable to capture output.')
        print()
        print('To verify it worked, check HA logs:')
        print('  Developer Tools → Logs → filter \"llmvision\"')
    else:
        print(f'Unexpected: {d}')
except Exception as e:
    print(f'Parse error: {e}')
    print(f'Raw: {sys.stdin.read()}')
" 2>/dev/null

echo ""
echo "=== Alternative: Test via Developer Tools ==="
echo "1. Go to HA → Developer Tools → Services"
echo "2. Select: llmvision.image_analyzer"
echo "3. Fill in:"
echo "   - provider: $OLLAMA_PROVIDER"
echo "   - model: llava:7b"
echo "   - image_entity: $IMAGE_ENTITY"
echo "   - message: $PROMPT"
echo "4. Click 'Call Service' - response appears in trace"
