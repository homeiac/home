#!/bin/bash
# Measure peak GPU memory + latency of an Ollama vision model on the shared RTX 3070 (read-only apart from loading the model)
#
# Usage: ./scripts/ollama/measure-vlm-vram.sh <model> <num_ctx> <image.jpg>...
#   e.g. ./scripts/ollama/measure-vlm-vram.sh qwen2.5vl:3b 16384 f1.jpg f2.jpg ... f8.jpg
# Needs: KUBECONFIG (scripts/k3s/get-kubeconfig.sh), python3. Port-forwards svc/ollama-lb locally, sends ONE chat request with all
# images (video-frames case: pass several), polls nvidia-smi inside the pod every second, prints baseline / peak / latency.
# Context matters: each 1024px frame is ~1000 tokens for Qwen2.5-VL; Ollama's default num_ctx (4096) would truncate 8 frames.
# Env: VLM_TIMEOUT (s per call, default 900), VLM_NUM_BATCH (Ollama num_batch; smaller = smaller compute buffer). Prints how many layers Ollama put on the GPU.
# VLM_THINK=false sends think:false (thinking models otherwise burn hundreds of hidden tokens per reply).
# Unloads the model afterwards (keep_alive 0) so VRAM returns to baseline.
set -euo pipefail
export KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"
MODEL="${1:?model}"; NUM_CTX="${2:?num_ctx}"; shift 2; [[ $# -ge 1 ]] || { echo "need at least one image"; exit 1; }
PORT="${LOCAL_PORT:-21434}"
kubectl port-forward -n ollama svc/ollama-lb "$PORT:80" >/dev/null 2>&1 & PF=$!
SMI_LOG="$(mktemp)"; trap 'kill $PF $POLL 2>/dev/null || true; rm -f "$SMI_LOG"' EXIT
for _ in $(seq 1 20); do curl -sf "http://127.0.0.1:$PORT/" >/dev/null 2>&1 && break; sleep 0.5; done
smi() { kubectl exec -n ollama deploy/ollama-gpu -- nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits; }
echo "baseline used/total MiB: $(smi)"
( while true; do smi >> "$SMI_LOG" 2>/dev/null; sleep 1; done ) & POLL=$!
python3 - "$PORT" "$MODEL" "$NUM_CTX" "$@" <<'PY' || echo "REQUEST FAILED (timeout/500): peak below is still valid"
import base64, json, sys, time, urllib.request
port, model, num_ctx, *imgs = sys.argv[1:]
content = "Describe what is happening across these %d frames in 2 sentences." % len(imgs)
body = {"model": model, "stream": False, **({"think": False} if __import__("os").environ.get("VLM_THINK") == "false" else {}), "keep_alive": 0, "options": dict({"num_ctx": int(num_ctx), "temperature": 0.2}, **({"num_batch": int(__import__("os").environ["VLM_NUM_BATCH"])} if "VLM_NUM_BATCH" in __import__("os").environ else {})),
        "messages": [{"role": "user", "content": content, "images": [base64.b64encode(open(p, "rb").read()).decode() for p in imgs]}]}
t = time.time()
r = json.load(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:%s/api/chat" % port, json.dumps(body).encode(), {"Content-Type": "application/json"}), timeout=int(__import__("os").environ.get("VLM_TIMEOUT", "900"))))
print("latency s: %.1f | prompt_tokens: %s | eval_tokens: %s | load_s: %.1f" % (time.time() - t, r.get("prompt_eval_count"), r.get("eval_count"), r.get("load_duration", 0) / 1e9))
print("reply:", r["message"]["content"][:300].replace("\n", " "))
PY
kill $POLL 2>/dev/null || true
echo "ollama: $(kubectl logs -n ollama deploy/ollama-gpu --since=15m 2>&1 | grep -E 'offloaded [0-9]+/[0-9]+ layers|compute graph' | sed 's/.*msg=//' | tail -2 | tr '\n' ' ')"
echo "peak used MiB: $(cut -d, -f1 "$SMI_LOG" | sort -n | tail -1) of $(head -1 "$SMI_LOG" | cut -d, -f2)"
