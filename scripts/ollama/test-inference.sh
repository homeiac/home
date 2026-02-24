#!/bin/bash
# Test Ollama inference speed
# Usage: test-inference.sh [model] [prompt]
#
# Examples:
#   test-inference.sh                           # default: qwen2.5:7b "what time is it?"
#   test-inference.sh qwen2.5:3b                # specific model
#   test-inference.sh qwen2.5:3b "say hello"    # specific model + prompt

set -e

KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"
export KUBECONFIG

OLLAMA_NS="${OLLAMA_NS:-ollama}"
MODEL="${1:-qwen2.5:7b}"
PROMPT="${2:-what time is it?}"

# Get Ollama URL
OLLAMA_IP=$(kubectl get svc -n "$OLLAMA_NS" -o jsonpath='{.items[0].status.loadBalancer.ingress[0].ip}' 2>/dev/null)
OLLAMA_PORT=$(kubectl get svc -n "$OLLAMA_NS" -o jsonpath='{.items[0].spec.ports[0].port}' 2>/dev/null)
OLLAMA_URL="http://${OLLAMA_IP}:${OLLAMA_PORT:-80}"

echo "Model:  $MODEL"
echo "Prompt: $PROMPT"
echo "URL:    $OLLAMA_URL"
echo ""
echo "Waiting for response..."

RESPONSE=$(curl -s --connect-timeout 10 -w "\n__TIME__%{time_total}" \
    -X POST "$OLLAMA_URL/api/generate" \
    -d "{\"model\":\"$MODEL\",\"prompt\":\"$PROMPT\",\"stream\":false}" 2>/dev/null)

WALL_TIME=$(echo "$RESPONSE" | grep "__TIME__" | sed 's/__TIME__//')
JSON=$(echo "$RESPONSE" | grep -v "__TIME__")

if [[ -z "$JSON" ]]; then
    echo "ERROR: No response from Ollama"
    exit 1
fi

echo "$JSON" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    resp = d.get('response', 'N/A')
    load_s = d.get('load_duration', 0) / 1e9
    prompt_s = d.get('prompt_eval_duration', 0) / 1e9
    eval_s = d.get('eval_duration', 0) / 1e9
    total_s = d.get('total_duration', 0) / 1e9
    tokens = d.get('eval_count', 0)
    tps = tokens / eval_s if eval_s > 0 else 0

    print(f'Response: {resp[:200]}')
    print(f'')
    print(f'--- Timing ---')
    print(f'  Model load: {load_s:6.1f}s')
    print(f'  Prompt:     {prompt_s:6.1f}s')
    print(f'  Inference:  {eval_s:6.1f}s ({tokens} tokens)')
    print(f'  Total:      {total_s:6.1f}s')
    print(f'  Speed:      {tps:.1f} tokens/sec')
    print(f'')
    if tps < 5:
        print(f'  ⚠ SLOW — likely running on CPU. Check GPU with check-ollama.sh')
    elif tps < 20:
        print(f'  OK — partial GPU offload')
    else:
        print(f'  FAST — full GPU acceleration')
except Exception as e:
    print(f'ERROR: {e}')
    sys.exit(1)
"
