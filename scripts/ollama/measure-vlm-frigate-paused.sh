#!/bin/bash
# Measure a vision model on the RTX 3070 with Frigate PAUSED, always restoring Frigate afterwards (issue #212)
#
# Usage: ./scripts/ollama/measure-vlm-frigate-paused.sh <model> [max_seconds_per_call=240]
#   e.g. ./scripts/ollama/measure-vlm-frigate-paused.sh qwen2.5vl:3b
# Pause = Flux per-object annotation (so Flux does not undo it) + scale deployment/frigate to 0. Restore (trap: runs on success,
# failure, Ctrl-C, kill) = scale to 1 + remove the annotation + wait for rollout. Git is never modified. Frigate is blind meanwhile.
# Cases: A) 1 photo 1024px (run twice: cold load, then warm), B) 4 frames 640px ctx 8192, C) 8 frames 640px ctx 12288.
set -uo pipefail
export KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL="${1:?model}"; export VLM_TIMEOUT="${2:-240}"
W="$(mktemp -d)"
restore() {
  echo ">>> restoring Frigate"
  kubectl scale deploy/frigate -n frigate --replicas=1
  kubectl annotate deploy/frigate -n frigate kustomize.toolkit.fluxcd.io/reconcile- >/dev/null 2>&1
  kubectl rollout status deploy/frigate -n frigate --timeout=300s
  rm -rf "$W"
}
trap restore EXIT
for i in 1 2 3 4 5 6 7 8; do
  ffmpeg -v error -f lavfi -i "testsrc=size=1024x768:rate=1" -frames:v 1 "$W/big$i.jpg"
  ffmpeg -v error -i "$W/big$i.jpg" -vf scale=640:-2 "$W/s$i.jpg"
done
echo ">>> pausing Frigate (annotation + scale 0)"
kubectl annotate deploy/frigate -n frigate kustomize.toolkit.fluxcd.io/reconcile=disabled --overwrite >/dev/null
kubectl scale deploy/frigate -n frigate --replicas=0
kubectl wait --for=delete pod -l app=frigate -n frigate --timeout=120s >/dev/null 2>&1
sleep 5
echo "GPU now: $(kubectl exec -n ollama deploy/ollama-gpu -- nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader)"
echo "=== A1 cold: 1 photo 1024px ctx 4096";  "$HERE/measure-vlm-vram.sh" "$MODEL" 4096 "$W/big1.jpg" 2>&1 | grep -v "Terminated\|smi >>\|^done"
echo "=== A2 warm-ish: same again";           "$HERE/measure-vlm-vram.sh" "$MODEL" 4096 "$W/big1.jpg" 2>&1 | grep -v "Terminated\|smi >>\|^done"
echo "=== B 4 frames 640px ctx 8192";         "$HERE/measure-vlm-vram.sh" "$MODEL" 8192 "$W/s1.jpg" "$W/s2.jpg" "$W/s3.jpg" "$W/s4.jpg" 2>&1 | grep -v "Terminated\|smi >>\|^done"
echo "=== C 8 frames 640px ctx 12288";        "$HERE/measure-vlm-vram.sh" "$MODEL" 12288 "$W"/s?.jpg 2>&1 | grep -v "Terminated\|smi >>\|^done"
