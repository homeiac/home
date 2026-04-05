#!/bin/bash
# Test Ollama vision (multimodal) capability with a camera snapshot
# Usage: test-vision.sh [model] [camera_entity]
#
# Examples:
#   test-vision.sh                                    # default: gemma4:e2b + doorbell
#   test-vision.sh gemma4:e2b camera.reolink_video_doorbell_wifi_fluent
#   test-vision.sh llava:7b camera.trendnet_ip_572w
#
# Requires: HA_TOKEN in proxmox/homelab/.env, Ollama API reachable

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"
export KUBECONFIG

MODEL="${1:-gemma4:e2b}"
CAMERA="${2:-camera.reolink_video_doorbell_wifi_fluent}"
TMPDIR_WORK=$(mktemp -d)
trap 'rm -rf "$TMPDIR_WORK"' EXIT

# Load HA token
ENV_FILE="$SCRIPT_DIR/../../proxmox/homelab/.env"
if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi
[[ -z "$HA_TOKEN" ]] && { echo "ERROR: HA_TOKEN not found"; exit 1; }
HA_URL="${HA_URL:-http://homeassistant.maas:8123}"

# Get Ollama URL
OLLAMA_NS="${OLLAMA_NS:-ollama}"
OLLAMA_IP=$(kubectl get svc -n "$OLLAMA_NS" -o jsonpath='{.items[0].status.loadBalancer.ingress[0].ip}' 2>/dev/null)
OLLAMA_PORT=$(kubectl get svc -n "$OLLAMA_NS" -o jsonpath='{.items[0].spec.ports[0].port}' 2>/dev/null)
OLLAMA_URL="http://${OLLAMA_IP}:${OLLAMA_PORT:-80}"

echo "=== Ollama Vision Test ==="
echo "Model:   $MODEL"
echo "Camera:  $CAMERA"
echo "Ollama:  $OLLAMA_URL"
echo ""

# Step 1: Grab camera snapshot via HA API
echo "--- Step 1: Taking snapshot ---"
curl -s --max-time 15 \
    -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/camera_proxy/$CAMERA" \
    -o "$TMPDIR_WORK/snapshot.jpg" 2>/dev/null

if [[ ! -s "$TMPDIR_WORK/snapshot.jpg" ]]; then
    echo "ERROR: Failed to get snapshot from $CAMERA"
    exit 1
fi

IMG_SIZE=$(wc -c < "$TMPDIR_WORK/snapshot.jpg" | tr -d ' ')
IMG_INFO=$(file "$TMPDIR_WORK/snapshot.jpg" | sed 's/.*: //')
echo "OK: $IMG_INFO ($IMG_SIZE bytes)"
echo ""

# Step 2: Base64 encode and build payload
echo "--- Step 2: Sending to $MODEL ---"
IMG_B64=$(base64 < "$TMPDIR_WORK/snapshot.jpg")

python3 -c "
import json
payload = {
    'model': '$MODEL',
    'prompt': 'Analyze this camera image and describe any activity detected. Focus on people, vehicles, and movement. If no clear activity is visible, describe why - such as image too dark, empty scene, etc. Be specific and concise.',
    'images': ['''$IMG_B64'''],
    'stream': False,
    'think': False,
    'options': {'num_predict': 200}
}
with open('$TMPDIR_WORK/payload.json', 'w') as f:
    json.dump(payload, f)
print(f'Payload size: {len(json.dumps(payload)) / 1024:.0f} KB')
"

echo "Waiting for response (may take 30-60s on first load)..."
echo ""

# Step 3: Call Ollama API
curl -s --max-time 120 \
    -X POST "$OLLAMA_URL/api/generate" \
    -H "Content-Type: application/json" \
    -d @"$TMPDIR_WORK/payload.json" \
    > "$TMPDIR_WORK/response.json" 2>/dev/null

# Step 4: Parse results
echo "--- Results ---"
python3 -c "
import json, sys
try:
    with open('$TMPDIR_WORK/response.json') as f:
        d = json.load(f)

    resp = d.get('response', '')
    thinking = d.get('thinking', '')
    load_s = d.get('load_duration', 0) / 1e9
    prompt_s = d.get('prompt_eval_duration', 0) / 1e9
    eval_s = d.get('eval_duration', 0) / 1e9
    total_s = d.get('total_duration', 0) / 1e9
    tokens = d.get('eval_count', 0)
    prompt_tokens = d.get('prompt_eval_count', 0)
    tps = tokens / eval_s if eval_s > 0 else 0

    if resp.strip():
        print(f'Response: {resp.strip()}')
    elif thinking.strip():
        print(f'[Model used thinking mode - response in thinking field]')
        print(f'Thinking: {thinking.strip()[:500]}')
    else:
        print(f'WARNING: Empty response (both response and thinking fields)')
        print(f'Raw keys: {list(d.keys())}')
        # Show first 200 chars of raw response for debugging
        raw = json.dumps(d)[:200]
        print(f'Raw (truncated): {raw}')

    print()
    print(f'--- Timing ---')
    print(f'  Model load:    {load_s:6.1f}s')
    print(f'  Prompt eval:   {prompt_s:6.1f}s ({prompt_tokens} tokens)')
    print(f'  Generation:    {eval_s:6.1f}s ({tokens} tokens)')
    print(f'  Total:         {total_s:6.1f}s')
    print(f'  Speed:         {tps:.1f} tokens/sec')
    print()

    if not resp.strip() and not thinking.strip():
        print('VERDICT: FAIL - model returned empty response for image')
        print('This model may not support vision or needs different parameters.')
    elif tps < 5:
        print('VERDICT: SLOW - likely CPU inference')
    elif tps < 10:
        print('VERDICT: MARGINAL - partial GPU offload')
    else:
        print('VERDICT: PASS - fast GPU inference with vision')
except Exception as e:
    print(f'ERROR parsing response: {e}')
    with open('$TMPDIR_WORK/response.json') as f:
        print(f'Raw: {f.read()[:300]}')
"
echo ""
