#!/usr/bin/env bash
# Ask Flux to read committed configuration; never manually apply application YAML.
set -euo pipefail
export KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"
requested=$(date -u +%Y-%m-%dT%H:%M:%SZ)
kubectl --request-timeout=20s -n flux-system annotate gitrepository photo-enrichment-preview reconcile.fluxcd.io/requestedAt="$requested" --overwrite
kubectl --request-timeout=20s -n flux-system annotate kustomization photo-enrichment-preview reconcile.fluxcd.io/requestedAt="$requested" --overwrite
# Wait for the source revision actually committed in this checkout.
revision=$(git -C "$(dirname "${BASH_SOURCE[0]}")/../.." rev-parse HEAD)
for attempt in $(seq 1 36); do
  applied=$(kubectl --request-timeout=20s -n flux-system get kustomization photo-enrichment-preview -o jsonpath='{.status.lastAppliedRevision}')
  [[ "$applied" == *"$revision" ]] && break
  [[ "$attempt" -lt 36 ]] || { echo 'Flux has not applied the requested commit'; exit 1; }
  sleep 5
done
kubectl --request-timeout=20s -n immich-pilot annotate helmrelease immich reconcile.fluxcd.io/requestedAt="$requested" --overwrite
for attempt in $(seq 1 36); do
  handled=$(kubectl --request-timeout=20s -n immich-pilot get helmrelease immich -o jsonpath='{.status.lastHandledReconcileAt}')
  [[ "$handled" == "$requested" ]] && break
  [[ "$attempt" -lt 36 ]] || { echo 'Helm reconciliation has not completed'; exit 1; }
  sleep 5
done
kubectl --request-timeout=20s -n immich-pilot get helmrelease immich
kubectl --request-timeout=20s -n immich-pilot rollout status deployment/immich-server --timeout=60s
bash "$(dirname "${BASH_SOURCE[0]}")/inspect-auth.sh"
