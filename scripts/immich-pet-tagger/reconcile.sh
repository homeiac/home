#!/usr/bin/env bash
# Reconcile the already-pushed photo branch; do not kubectl apply resources.
set -euo pipefail
export KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"
requested=$(date -u +%Y-%m-%dT%H:%M:%SZ)
kubectl -n flux-system annotate gitrepository photo-enrichment-preview \
  reconcile.fluxcd.io/requestedAt="$requested" --overwrite
kubectl -n flux-system annotate kustomization photo-enrichment-preview \
  reconcile.fluxcd.io/requestedAt="$requested" --overwrite
kubectl -n flux-system get kustomization photo-enrichment-preview
