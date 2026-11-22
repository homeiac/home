#!/usr/bin/env bash
# Read the source revision, reconciliation state and caption installer logs.
set -euo pipefail
export KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"
kubectl -n flux-system get gitrepository photo-enrichment-preview
kubectl -n flux-system get kustomization photo-enrichment-preview
kubectl -n monitoring get cronjob caption-worker-reconcile
kubectl -n monitoring get pods -l app=caption-worker-installer -o wide
kubectl -n monitoring logs -l app=caption-worker-installer --all-containers --tail=15 --prefix --max-log-requests=10
