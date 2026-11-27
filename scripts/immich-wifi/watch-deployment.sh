#!/usr/bin/env bash
# Compact read-only status for the Flux revision and host deployment Job.
set -euo pipefail
export KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"
kubectl --request-timeout=20s -n flux-system get gitrepository photo-enrichment-preview
kubectl --request-timeout=20s -n flux-system get kustomization photo-enrichment-preview
kubectl --request-timeout=20s -n monitoring get job immich-wifi-deploy -o wide
kubectl --request-timeout=20s -n monitoring logs job/immich-wifi-deploy --tail=45
