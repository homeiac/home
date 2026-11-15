#!/bin/bash
# Ask Flux to sync from git now, and wait until a Kustomization applies the new revision
#
# Usage: ./reconcile.sh [kustomization]      (default: flux-system)
#
# Equivalent of `flux reconcile kustomization <name> --with-source`, without needing the flux CLI
# or a kubeconfig on this machine: kubectl runs inside the K3s VM (cb_kubectl). Annotates the
# GitRepository and the Kustomization with reconcile.fluxcd.io/requestedAt, then polls (up to
# 5 min) until the Kustomization reports Ready with the GitRepository's latest revision.
# Idempotent: re-running just requests another sync.

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../backup/cloud-backup-common.sh"

readonly KS="${1:-flux-system}"
readonly NS=flux-system
now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

cb_kubectl -n "$NS" annotate --overwrite gitrepository/flux-system "reconcile.fluxcd.io/requestedAt=$now" >/dev/null
cb_kubectl -n "$NS" annotate --overwrite "kustomization/$KS" "reconcile.fluxcd.io/requestedAt=$now" >/dev/null
echo "[$(date +%H:%M:%S)] requested sync of gitrepository/flux-system and kustomization/$KS"

for i in $(seq 1 30); do
  sleep 10
  src="$(cb_kubectl -n "$NS" get gitrepository flux-system -o jsonpath='{.status.artifact.revision}' 2>/dev/null || true)"
  app="$(cb_kubectl -n "$NS" get "kustomization/$KS" -o jsonpath='{.status.lastAppliedRevision}' 2>/dev/null || true)"
  ready="$(cb_kubectl -n "$NS" get "kustomization/$KS" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.conditions[?(@.type=="Ready")].message}' 2>/dev/null || true)"
  echo "[$(date +%H:%M:%S)] source=${src:0:20} applied=${app:0:20} ready=${ready:0:160}"
  if [[ -n "$src" && "$src" == "$app" && "$ready" == True* ]]; then echo "Applied $app"; exit 0; fi
done
echo "ERROR: $KS did not apply the latest revision within 5 min"; exit 1
