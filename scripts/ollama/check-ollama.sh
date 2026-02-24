#!/bin/bash
# Check Ollama status: pod, API, models, GPU, and loaded models
# Usage: check-ollama.sh [--json]
#
# Checks:
#   1. Ollama pod status in K8s
#   2. API reachability via LoadBalancer
#   3. Available models
#   4. Currently loaded models (ollama ps)
#   5. GPU utilization (nvidia-smi)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"
export KUBECONFIG

OLLAMA_NS="${OLLAMA_NS:-ollama}"
JSON_OUTPUT=false
[[ "${1:-}" == "--json" ]] && JSON_OUTPUT=true

echo "=== Ollama Status Check ==="
echo ""

# 1. Pod status
echo "--- Pod Status ---"
kubectl get pods -n "$OLLAMA_NS" -o wide 2>/dev/null || echo "ERROR: Cannot reach K8s cluster"
echo ""

# 2. Service/LoadBalancer IP
echo "--- Service ---"
OLLAMA_IP=$(kubectl get svc -n "$OLLAMA_NS" -o jsonpath='{.items[0].status.loadBalancer.ingress[0].ip}' 2>/dev/null)
OLLAMA_PORT=$(kubectl get svc -n "$OLLAMA_NS" -o jsonpath='{.items[0].spec.ports[0].port}' 2>/dev/null)
OLLAMA_URL="http://${OLLAMA_IP}:${OLLAMA_PORT:-80}"
echo "URL: $OLLAMA_URL"
echo ""

# 3. API check + models
echo "--- Available Models ---"
if curl -s --connect-timeout 5 "$OLLAMA_URL/api/tags" 2>/dev/null | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    for m in d.get('models', []):
        size_gb = m['size'] / 1e9
        print(f'  {m[\"name\"]:25s} {size_gb:.1f} GB  ({m[\"details\"][\"parameter_size\"]})')
except:
    print('  ERROR: Could not parse response')
    sys.exit(1)
" 2>/dev/null; then
    echo ""
else
    echo "  ERROR: Ollama API unreachable at $OLLAMA_URL"
    echo ""
fi

# 4. Loaded models (ollama ps)
echo "--- Loaded Models ---"
POD=$(kubectl get pods -n "$OLLAMA_NS" -l app=ollama-gpu -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [[ -n "$POD" ]]; then
    kubectl exec -n "$OLLAMA_NS" "$POD" -- ollama ps 2>/dev/null || echo "  No models loaded or exec failed"
else
    echo "  ERROR: No ollama pod found"
fi
echo ""

# 5. GPU status
echo "--- GPU Status ---"
if [[ -n "$POD" ]]; then
    kubectl exec -n "$OLLAMA_NS" "$POD" -- nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu --format=csv,noheader 2>/dev/null || echo "  No GPU or nvidia-smi not available"
else
    echo "  ERROR: No ollama pod found"
fi
echo ""

# 6. HA integration status (if ha-api.sh available)
if [[ -f "$SCRIPT_DIR/../lib-sh/ha-api.sh" ]]; then
    echo "--- HA Integration ---"
    source "$SCRIPT_DIR/../lib-sh/ha-api.sh"
    ha_api_get "config/config_entries/entry" 2>/dev/null | \
        jq -r '.[] | select(.domain == "ollama") | "  State: \(.state)\n  URL:   \(.title)"' 2>/dev/null || echo "  Could not check HA integration"
    echo ""
fi
