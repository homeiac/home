#!/usr/bin/env bash
# Inspect rollout, PVC and HTTPS without exposing secret values.
set -euo pipefail
export KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"
kubectl -n immich-pilot get deployment,pod,pvc,service -l app=immich-pet-tagger
kubectl -n immich-pilot get pvc immich-pet-tagger
curl --fail --silent --show-error --max-time 15 \
  https://pets.app.home.panderosystems.com/health
