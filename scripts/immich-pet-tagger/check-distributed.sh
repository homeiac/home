#!/usr/bin/env bash
# Read-only rollout and health checks for the PostgreSQL queue and CPU workers.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"
kubectl -n flux-system get kustomization photo-enrichment-preview
kubectl -n database get job waffles-schema-v2
kubectl -n database wait --for=condition=complete job/waffles-schema-v2 --timeout=60s
for workload in waffles-queue waffles-worker-pve waffles-worker-still-fawn; do
  kubectl -n immich-pilot rollout status "deployment/$workload" --timeout=60s
done
kubectl -n immich-pilot get pods -l 'app in (waffles-queue,waffles-worker-pve,waffles-worker-still-fawn)'
python3 "$SCRIPT_DIR/check-queue.py"
python3 "$SCRIPT_DIR/distributed.py" tuning
python3 "$SCRIPT_DIR/distributed.py" status --compact
