#!/usr/bin/env bash
# Bootstrap a narrowly scoped Flux preview for PR #218, not the whole feature branch.
# Remove these two preview objects when the route is owned by the main Flux source.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"
# Flux owns the service/route/middleware. No camera or existing application changes.
kubectl apply -f - <<'YAML'
apiVersion: source.toolkit.fluxcd.io/v1
kind: GitRepository
metadata:
  name: photo-enrichment-preview
  namespace: flux-system
spec:
  interval: 1m
  url: ssh://git@github.com/homeiac/home
  ref:
    branch: codex/photo-enrichment-217
  secretRef:
    name: flux-system
---
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: photo-enrichment-preview
  namespace: flux-system
spec:
  interval: 1m
  path: ./gitops/clusters/homelab/apps/photo-enrichment
  prune: true
  sourceRef:
    kind: GitRepository
    name: photo-enrichment-preview
  timeout: 2m
  decryption:
    provider: sops
    secretRef:
      name: sops-age
YAML
kubectl -n flux-system wait gitrepository/photo-enrichment-preview --for=condition=ready --timeout=60s
kubectl -n flux-system wait kustomization/photo-enrichment-preview --for=condition=ready --timeout=60s
