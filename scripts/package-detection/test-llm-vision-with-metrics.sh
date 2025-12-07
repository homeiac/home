#!/bin/bash
# Test LLM Vision with CPU/GPU monitoring on HA and Ollama
# Compares Frigate snapshot vs Reolink direct camera

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../../proxmox/homelab/.env"

HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2)
HA_URL="http://192.168.4.240:8123"
OLLAMA_URL="http://192.168.4.81"
export KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"

# LLM Vision provider
OLLAMA_PROVIDER="01K1KDVH6Y1GMJ69MJF77WGJEA"

PROMPT="Answer YES or NO only: Is there a package visible?"

# Function to get GPU stats from K8s
get_gpu_stats() {
    kubectl exec -n ollama deploy/ollama-gpu -- \
        nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv,noheader 2>/dev/null || echo "N/A"
}

# Function to get K8s pod CPU/memory
get_pod_stats() {
    kubectl top pod -n ollama --no-headers 2>/dev/null | awk '{print "CPU: "$2" | Mem: "$3}' || echo "N/A"
}

# Function to get Ollama loaded models
get_ollama_models() {
    curl -s "$OLLAMA_URL/api/ps" 2>/dev/null | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    models = d.get('models', [])
    if models:
        parts = []
        for m in models:
            name = m.get('name', 'unknown')
            vram = m.get('size_vram', 0) / (1024**3)
            parts.append(f'{name} ({vram:.1f}GB)')
        print(', '.join(parts))
    else:
        print('None loaded')
except:
    print('Error')
" 2>/dev/null
}

# Force load llava model
load_llava() {
    echo "   Loading llava:7b (this may take a moment)..."
    curl -s -X POST "$OLLAMA_URL/api/generate" \
        -d '{"model": "llava:7b", "prompt": "hi", "stream": false}' > /dev/null 2>&1
    sleep 2
}

# Function to call LLM Vision and measure time
test_image() {
    local IMAGE_ENTITY="$1"
    local LABEL="$2"

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Testing: $LABEL"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Entity: $IMAGE_ENTITY"
    echo ""

    echo "📊 BEFORE:"
    echo "   GPU: $(get_gpu_stats)"
    echo "   Pod: $(get_pod_stats)"
    echo "   Model: $(get_ollama_models)"
    echo ""

    echo "🔄 Calling LLM Vision..."
    START_TIME=$(python3 -c "import time; print(time.time())")

    RESPONSE=$(curl -s -X POST \
        -H "Authorization: Bearer $HA_TOKEN" \
        -H "Content-Type: application/json" \
        -d "{
            \"provider\": \"$OLLAMA_PROVIDER\",
            \"model\": \"llava:7b\",
            \"image_entity\": [\"$IMAGE_ENTITY\"],
            \"message\": \"$PROMPT\",
            \"max_tokens\": 10,
            \"target_width\": 1280
        }" \
        "$HA_URL/api/services/llmvision/image_analyzer?return_response=true" 2>&1)

    END_TIME=$(python3 -c "import time; print(time.time())")
    DURATION=$(python3 -c "print(f'{$END_TIME - $START_TIME:.2f}')")

    echo ""
    echo "📊 AFTER:"
    echo "   GPU: $(get_gpu_stats)"
    echo "   Pod: $(get_pod_stats)"
    echo "   Model: $(get_ollama_models)"
    echo ""

    # Parse response
    ANSWER=$(echo "$RESPONSE" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    if 'service_response' in d:
        print(d['service_response'].get('response_text', 'no text'))
    elif isinstance(d, list) and len(d) == 0:
        print('(empty - check HA logs)')
    else:
        print(str(d)[:80])
except Exception as e:
    print(f'error: {e}')
" 2>/dev/null)

    echo "📝 RESULT:"
    echo "   LLM says: $ANSWER"
    echo "   ⏱️  Time: ${DURATION}s"

    if echo "$ANSWER" | grep -qi "yes"; then
        echo "   ✅ PACKAGE DETECTED"
    elif echo "$ANSWER" | grep -qi "no"; then
        echo "   ❌ No package"
    else
        echo "   ⚠️  Unexpected response"
    fi
}

# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  LLM Vision Performance Test"
echo "═══════════════════════════════════════════════════════"
echo ""
echo "Comparing:"
echo "  1. Frigate person snapshot (pre-processed image)"
echo "  2. Reolink direct camera (live feed)"
echo ""

# Ensure llava is loaded
echo "🔧 Checking llava:7b..."
CURRENT_MODEL=$(get_ollama_models)
if [[ "$CURRENT_MODEL" != *"llava"* ]]; then
    load_llava
fi
echo "   Model ready: $(get_ollama_models)"
echo ""

# Baseline stats
echo "📊 BASELINE:"
echo "   GPU: $(get_gpu_stats)"
echo "   Pod: $(get_pod_stats)"

# Test 1: Frigate snapshot (image entity)
test_image "image.reolink_doorbell_person" "Frigate Person Snapshot"

echo ""
echo "(waiting 3s before next test...)"
sleep 3

# Test 2: Reolink direct camera
test_image "camera.reolink_doorbell" "Reolink Direct Camera"

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  Summary"
echo "═══════════════════════════════════════════════════════"
echo ""
echo "For detailed monitoring:"
echo "  • Proxmox: VM 116 (HA) CPU usage"
echo "  • Grafana: K8s GPU metrics dashboard"
echo "  • Terminal: kubectl top pod -n ollama --watch"
echo ""
