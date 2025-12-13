#!/bin/bash
set -euo pipefail

export KUBECONFIG=~/kubeconfig

echo "Reconciling Flux..."
flux reconcile kustomization flux-system --with-source

echo "Waiting for Frigate pod..."
kubectl wait --for=condition=ready pod -l app=frigate -n frigate --timeout=120s

echo "Checking pod location..."
kubectl get pods -n frigate -o wide

echo "Checking Coral detector..."
kubectl exec -n frigate deployment/frigate -- curl -s http://localhost:5000/api/stats | jq '.detectors'

echo "Checking cameras..."
kubectl exec -n frigate deployment/frigate -- curl -s http://localhost:5000/api/stats | jq '.cameras | keys'

echo "Migration complete!"
