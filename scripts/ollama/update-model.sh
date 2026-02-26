#!/bin/bash
# Swap Ollama model: pull new model, remove old, verify GPU loading
# Usage: update-model.sh [new_model] [old_model]
#
# Examples:
#   update-model.sh                            # default: pull qwen3:4b, remove qwen2.5:3b
#   update-model.sh qwen3:4b                   # pull qwen3:4b only (no removal)
#   update-model.sh qwen3:4b qwen2.5:3b        # pull new, remove old
#
# This script:
#   1. Pulls the new model via Ollama API
#   2. Verifies the new model loaded on GPU
#   3. Removes the old model to free PVC space (if specified)
#   4. Updates HA conversation agent (optional, with --ha flag)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"
export KUBECONFIG

OLLAMA_NS="${OLLAMA_NS:-ollama}"
NEW_MODEL="${1:-qwen3:4b}"
OLD_MODEL="${2:-qwen2.5:3b}"
UPDATE_HA=false

# Parse flags
for arg in "$@"; do
    [[ "$arg" == "--ha" ]] && UPDATE_HA=true
done

# Get pod name
POD=$(kubectl get pods -n "$OLLAMA_NS" -l app=ollama-gpu -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [[ -z "$POD" ]]; then
    echo "ERROR: No ollama-gpu pod found in namespace $OLLAMA_NS"
    exit 1
fi

# Get Ollama URL
OLLAMA_IP=$(kubectl get svc -n "$OLLAMA_NS" -o jsonpath='{.items[0].status.loadBalancer.ingress[0].ip}' 2>/dev/null)
OLLAMA_PORT=$(kubectl get svc -n "$OLLAMA_NS" -o jsonpath='{.items[0].spec.ports[0].port}' 2>/dev/null)
OLLAMA_URL="http://${OLLAMA_IP}:${OLLAMA_PORT:-80}"

echo "=== Ollama Model Swap ==="
echo "Pod:       $POD"
echo "URL:       $OLLAMA_URL"
echo "New model: $NEW_MODEL"
echo "Old model: $OLD_MODEL"
echo ""

# 1. Show current models
echo "--- Current Models ---"
kubectl exec -n "$OLLAMA_NS" "$POD" -- ollama list 2>/dev/null || echo "  No models found"
echo ""

# 2. Pull new model
echo "--- Pulling $NEW_MODEL ---"
echo "This may take a few minutes depending on model size..."
kubectl exec -n "$OLLAMA_NS" "$POD" -- ollama pull "$NEW_MODEL"
echo ""

# 3. Verify new model exists
echo "--- Verifying $NEW_MODEL ---"
if kubectl exec -n "$OLLAMA_NS" "$POD" -- ollama list 2>/dev/null | grep -q "$NEW_MODEL"; then
    echo "OK: $NEW_MODEL is available"
else
    echo "ERROR: $NEW_MODEL not found after pull"
    exit 1
fi
echo ""

# 4. Test inference on GPU
echo "--- Testing inference (GPU check) ---"
RESPONSE=$(curl -s --connect-timeout 30 --max-time 120 \
    -X POST "$OLLAMA_URL/api/generate" \
    -d "{\"model\":\"$NEW_MODEL\",\"prompt\":\"Say hello in one sentence.\",\"stream\":false}" 2>/dev/null)

echo "$RESPONSE" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    resp = d.get('response', 'N/A')
    eval_s = d.get('eval_duration', 0) / 1e9
    tokens = d.get('eval_count', 0)
    tps = tokens / eval_s if eval_s > 0 else 0
    print(f'  Response: {resp[:100]}')
    print(f'  Speed:    {tps:.1f} tokens/sec ({tokens} tokens in {eval_s:.1f}s)')
    if tps < 5:
        print(f'  WARNING: Likely running on CPU!')
    else:
        print(f'  OK: GPU acceleration confirmed')
except Exception as e:
    print(f'ERROR: {e}')
    sys.exit(1)
" 2>/dev/null
echo ""

# 5. GPU memory check
echo "--- GPU Memory ---"
kubectl exec -n "$OLLAMA_NS" "$POD" -- nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader 2>/dev/null || echo "  nvidia-smi unavailable"
echo ""

# 6. Remove old model (if different from new)
if [[ -n "$OLD_MODEL" && "$OLD_MODEL" != "$NEW_MODEL" ]]; then
    if kubectl exec -n "$OLLAMA_NS" "$POD" -- ollama list 2>/dev/null | grep -q "$OLD_MODEL"; then
        echo "--- Removing old model: $OLD_MODEL ---"
        kubectl exec -n "$OLLAMA_NS" "$POD" -- ollama rm "$OLD_MODEL"
        echo "Removed $OLD_MODEL"
    else
        echo "--- Old model $OLD_MODEL not present (skipping removal) ---"
    fi
    echo ""
fi

# 7. Final model list
echo "--- Final Models ---"
kubectl exec -n "$OLLAMA_NS" "$POD" -- ollama list 2>/dev/null
echo ""

# 8. Optionally update HA
if [[ "$UPDATE_HA" == true ]]; then
    echo "--- Updating HA conversation agent ---"
    "$SCRIPT_DIR/set-ha-model.sh" "$NEW_MODEL"
fi

echo "=== Done ==="
