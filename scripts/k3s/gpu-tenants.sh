#!/bin/bash
# Stop / start / show the workloads that share the RTX 3070 (except ollama-gpu, which serves the analysis)  (issue #212)
#
# Usage: ./scripts/k3s/gpu-tenants.sh stop|start|status
# Tenants (namespace/deployment): frigate/frigate, stable-diffusion/stable-diffusion-webui. Add new GPU workloads to TENANTS.
# stop : per Deployment: remember current replicas in annotation homelab.local/paused-replicas, set Flux annotation
#        kustomize.toolkit.fluxcd.io/reconcile=disabled (so Flux does not scale it back; Git is untouched), scale to 0.
# start: scale back to the remembered replica count, remove both annotations, wait for rollout.
# Idempotent. Frigate is blind (no detection/recording) while stopped. Needs KUBECONFIG (scripts/k3s/get-kubeconfig.sh).
set -euo pipefail
export KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"
TENANTS=("frigate/frigate" "stable-diffusion/stable-diffusion-webui")
PAUSED='homelab.local/paused-replicas'; FLUX='kustomize.toolkit.fluxcd.io/reconcile'
ann() { kubectl get deploy "$2" -n "$1" -o "jsonpath={.metadata.annotations.$3}" 2>/dev/null; }
case "${1:-}" in
  stop)
    for t in "${TENANTS[@]}"; do ns="${t%%/*}"; d="${t##*/}"
      cur="$(kubectl get deploy "$d" -n "$ns" -o jsonpath='{.spec.replicas}')"
      if [[ "$cur" == 0 && -n "$(kubectl get deploy "$d" -n "$ns" -o "jsonpath={.metadata.annotations}" | grep -o 'paused-replicas')" ]]; then echo "$t already stopped"; continue; fi
      kubectl annotate deploy "$d" -n "$ns" "$PAUSED=$cur" "$FLUX=disabled" --overwrite >/dev/null
      kubectl scale deploy "$d" -n "$ns" --replicas=0 >/dev/null
      echo "stopped $t (was $cur replicas)"
    done;;
  start)
    for t in "${TENANTS[@]}"; do ns="${t%%/*}"; d="${t##*/}"
      prev="$(kubectl get deploy "$d" -n "$ns" -o json | python3 -c 'import json,sys; print(json.load(sys.stdin)["metadata"].get("annotations",{}).get("homelab.local/paused-replicas",""))')"
      [[ -n "$prev" ]] || { echo "$t not stopped by this script (no $PAUSED annotation): left alone"; continue; }
      kubectl scale deploy "$d" -n "$ns" --replicas="$prev" >/dev/null
      kubectl annotate deploy "$d" -n "$ns" "$PAUSED-" "$FLUX-" >/dev/null
      kubectl rollout status deploy "$d" -n "$ns" --timeout=300s
      echo "started $t ($prev replicas)"
    done;;
  status) ;;
  *) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 1;;
esac
for t in "${TENANTS[@]}" ollama/ollama-gpu; do ns="${t%%/*}"; d="${t##*/}"
  printf '%-45s replicas=%s ready=%s\n' "$t" "$(kubectl get deploy "$d" -n "$ns" -o jsonpath='{.spec.replicas}')" "$(kubectl get deploy "$d" -n "$ns" -o jsonpath='{.status.readyReplicas}')"
done
echo "GPU: $(kubectl exec -n ollama deploy/ollama-gpu -- nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader)"
