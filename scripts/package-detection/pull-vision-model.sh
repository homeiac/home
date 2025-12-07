#!/bin/bash
# Pull a vision model to Ollama
# Usage: ./pull-vision-model.sh [model_name]
# Default: llava:7b

MODEL="${1:-llava:7b}"
OLLAMA_URL="http://192.168.4.81"

echo "=== Pulling $MODEL to Ollama ==="
echo "This may take several minutes for large models..."
echo ""

# Start pull (blocking, shows progress)
curl -X POST "$OLLAMA_URL/api/pull" \
    -d "{\"name\": \"$MODEL\", \"stream\": true}" \
    --no-buffer 2>/dev/null | while read -r line; do
    # Parse JSON progress
    status=$(echo "$line" | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); print(d.get('status',''))" 2>/dev/null)
    total=$(echo "$line" | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); print(d.get('total',0))" 2>/dev/null)
    completed=$(echo "$line" | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); print(d.get('completed',0))" 2>/dev/null)

    if [[ -n "$status" ]]; then
        if [[ "$total" -gt 0 && "$completed" -gt 0 ]]; then
            pct=$((completed * 100 / total))
            printf "\r%s: %d%%  " "$status" "$pct"
        else
            printf "\r%s          " "$status"
        fi
    fi
done

echo ""
echo ""
echo "=== Verifying model ==="
curl -s "$OLLAMA_URL/api/tags" | \
    python3 -c "
import sys, json
d = json.load(sys.stdin)
models = [m['name'] for m in d.get('models', [])]
if '$MODEL'.split(':')[0] in str(models):
    print('✅ $MODEL is now available')
else:
    print('❌ $MODEL not found. Available:', models)
"
