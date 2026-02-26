#!/bin/bash
# Swap Ollama model: pull new model, remove old, verify GPU loading
# Usage: update-model.sh [new_model] [old_model]
#
# Examples:
#   update-model.sh                            # default: pull qwen3:4b, remove qwen2.5:3b
#   update-model.sh qwen3:4b                   # pull qwen3:4b only (no removal)
#   update-model.sh qwen3:4b qwen2.5:3b        # pull new, remove old
#
# Environment:
#   OLLAMA_URL   - Ollama API base URL (auto-detected if not set)
#   NEW_MODEL    - Model to pull (overrides arg $1)
#   OLD_MODEL    - Model to remove (overrides arg $2)
#
# In-cluster (K8s Job): Uses Ollama HTTP API via service DNS
# On Mac: Falls back to kubectl to discover Ollama service IP

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

NEW_MODEL="${NEW_MODEL:-${1:-qwen3:4b}}"
OLD_MODEL="${OLD_MODEL:-${2:-qwen2.5:3b}}"
UPDATE_HA=false

# Parse flags
for arg in "$@"; do
    [[ "$arg" == "--ha" ]] && UPDATE_HA=true
done

# --- Determine execution mode ---
# In-cluster: KUBERNETES_SERVICE_HOST is set by K8s automatically
# Mac: use kubectl to discover Ollama service IP
if [[ -n "${KUBERNETES_SERVICE_HOST:-}" ]]; then
    # Running inside K8s cluster (Job pod)
    OLLAMA_URL="${OLLAMA_URL:-http://ollama-gpu.ollama.svc:80}"
    MODE="in-cluster"
elif [[ -n "${OLLAMA_URL:-}" ]]; then
    # Explicit URL provided (e.g., local testing)
    MODE="direct"
else
    # Running from Mac - discover via kubectl
    KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"
    export KUBECONFIG
    OLLAMA_NS="${OLLAMA_NS:-ollama}"
    OLLAMA_IP=$(kubectl get svc -n "$OLLAMA_NS" -o jsonpath='{.items[0].status.loadBalancer.ingress[0].ip}' 2>/dev/null)
    OLLAMA_PORT=$(kubectl get svc -n "$OLLAMA_NS" -o jsonpath='{.items[0].spec.ports[0].port}' 2>/dev/null)
    OLLAMA_URL="http://${OLLAMA_IP}:${OLLAMA_PORT:-80}"
    MODE="kubectl"
fi

echo "=== Ollama Model Swap ==="
echo "Mode:      $MODE"
echo "URL:       $OLLAMA_URL"
echo "New model: $NEW_MODEL"
echo "Old model: $OLD_MODEL"
echo ""

# --- Helper: check API reachable ---
check_api() {
    if ! curl -sf --connect-timeout 10 "$OLLAMA_URL/" >/dev/null 2>&1; then
        echo "ERROR: Ollama API unreachable at $OLLAMA_URL"
        exit 1
    fi
    echo "API: OK"
    echo ""
}

# --- 1. Show current models ---
show_models() {
    echo "--- Current Models ---"
    curl -s --connect-timeout 10 "$OLLAMA_URL/api/tags" 2>/dev/null | jq -r '
        .models[]? | "\(.name)\t\(.size / 1e9 | . * 10 | round / 10) GB\t\(.details.parameter_size // "?")"
    ' 2>/dev/null | column -t -s $'\t' || echo "  No models or API error"
    echo ""
}

# --- 2. Pull new model ---
pull_model() {
    echo "--- Pulling $NEW_MODEL ---"
    echo "This may take a few minutes depending on model size..."

    # Stream pull progress - the API returns JSON lines with status updates
    curl -s --connect-timeout 30 --max-time 600 \
        -X POST "$OLLAMA_URL/api/pull" \
        -d "{\"name\":\"$NEW_MODEL\",\"stream\":true}" \
        --no-buffer 2>/dev/null | while IFS= read -r line; do
        STATUS=$(echo "$line" | jq -r '.status // empty' 2>/dev/null)
        COMPLETED=$(echo "$line" | jq -r '.completed // empty' 2>/dev/null)
        TOTAL=$(echo "$line" | jq -r '.total // empty' 2>/dev/null)
        if [[ -n "$STATUS" ]]; then
            if [[ -n "$COMPLETED" && -n "$TOTAL" && "$TOTAL" != "0" ]]; then
                PCT=$(( COMPLETED * 100 / TOTAL ))
                printf "\r  %s: %d%%" "$STATUS" "$PCT"
            else
                printf "\r  %s                    " "$STATUS"
            fi
        fi
    done
    echo ""
    echo ""
}

# --- 3. Verify model exists ---
verify_model() {
    echo "--- Verifying $NEW_MODEL ---"
    if curl -s --connect-timeout 10 "$OLLAMA_URL/api/tags" 2>/dev/null | \
        jq -e ".models[]? | select(.name == \"$NEW_MODEL\")" >/dev/null 2>&1; then
        echo "OK: $NEW_MODEL is available"
    else
        # Also check without tag suffix (ollama may store as model:latest)
        MODEL_BASE="${NEW_MODEL%%:*}"
        if curl -s --connect-timeout 10 "$OLLAMA_URL/api/tags" 2>/dev/null | \
            jq -e ".models[]? | select(.name | startswith(\"$MODEL_BASE\"))" >/dev/null 2>&1; then
            echo "OK: $NEW_MODEL is available (matched by prefix)"
        else
            echo "ERROR: $NEW_MODEL not found after pull"
            exit 1
        fi
    fi
    echo ""
}

# --- 4. Test inference (GPU check) ---
test_inference() {
    echo "--- Testing inference (GPU check) ---"
    RESPONSE=$(curl -s --connect-timeout 30 --max-time 120 \
        -X POST "$OLLAMA_URL/api/generate" \
        -d "{\"model\":\"$NEW_MODEL\",\"prompt\":\"Say hello in one sentence.\",\"stream\":false}" 2>/dev/null)

    if [[ -z "$RESPONSE" ]]; then
        echo "  WARNING: No response from inference test"
        return
    fi

    # Parse with jq (no python dependency in alpine container)
    RESP_TEXT=$(echo "$RESPONSE" | jq -r '.response // "N/A"' 2>/dev/null | head -c 100)
    EVAL_NS=$(echo "$RESPONSE" | jq -r '.eval_duration // 0' 2>/dev/null)
    EVAL_COUNT=$(echo "$RESPONSE" | jq -r '.eval_count // 0' 2>/dev/null)

    if [[ "$EVAL_NS" -gt 0 && "$EVAL_COUNT" -gt 0 ]]; then
        # Calculate tokens/sec using integer math (no bc in alpine)
        # eval_duration is in nanoseconds
        EVAL_MS=$((EVAL_NS / 1000000))
        if [[ "$EVAL_MS" -gt 0 ]]; then
            TPS=$((EVAL_COUNT * 1000 / EVAL_MS))
            echo "  Response: $RESP_TEXT"
            echo "  Speed:    $TPS tokens/sec ($EVAL_COUNT tokens in ${EVAL_MS}ms)"
            if [[ "$TPS" -lt 5 ]]; then
                echo "  WARNING: Likely running on CPU!"
            else
                echo "  OK: GPU acceleration confirmed"
            fi
        fi
    else
        echo "  Response: $RESP_TEXT"
        echo "  WARNING: Could not calculate speed"
    fi
    echo ""
}

# --- 5. Remove old model ---
remove_old_model() {
    if [[ -z "$OLD_MODEL" || "$OLD_MODEL" == "$NEW_MODEL" ]]; then
        return
    fi

    # Check if old model exists
    if curl -s --connect-timeout 10 "$OLLAMA_URL/api/tags" 2>/dev/null | \
        jq -e ".models[]? | select(.name == \"$OLD_MODEL\")" >/dev/null 2>&1; then
        echo "--- Removing old model: $OLD_MODEL ---"
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 10 \
            -X DELETE "$OLLAMA_URL/api/delete" \
            -d "{\"name\":\"$OLD_MODEL\"}" 2>/dev/null)
        if [[ "$HTTP_CODE" == "200" ]]; then
            echo "Removed $OLD_MODEL"
        else
            echo "WARNING: Delete returned HTTP $HTTP_CODE"
        fi
    else
        echo "--- Old model $OLD_MODEL not present (skipping removal) ---"
    fi
    echo ""
}

# --- 6. Final model list ---
show_final() {
    echo "--- Final Models ---"
    curl -s --connect-timeout 10 "$OLLAMA_URL/api/tags" 2>/dev/null | jq -r '
        .models[]? | "\(.name)\t\(.size / 1e9 | . * 10 | round / 10) GB\t\(.details.parameter_size // "?")"
    ' 2>/dev/null | column -t -s $'\t' || echo "  Could not list models"
    echo ""
}

# --- Execute ---
check_api
show_models
pull_model
verify_model
test_inference
remove_old_model
show_final

# HA integration (only from Mac, not from in-cluster Job)
if [[ "$UPDATE_HA" == true && "$MODE" == "kubectl" ]]; then
    echo "--- Updating HA conversation agent ---"
    "$SCRIPT_DIR/set-ha-model.sh" "$NEW_MODEL"
fi

echo "=== Done ==="
