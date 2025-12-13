#!/bin/bash
set -euo pipefail

# Idempotent script to delete and recreate Frigate PVCs on still-fawn
# This is needed because local-path PVs have node affinity to the original node

export KUBECONFIG=~/kubeconfig

echo "=== Recreating Frigate PVCs for still-fawn ==="

# Delete PVCs if they exist (idempotent)
echo "Deleting existing PVCs (if any)..."
kubectl delete pvc frigate-config frigate-media -n frigate --ignore-not-found=true

# Wait for PVs to be released/deleted
echo "Waiting for PVs to be cleaned up..."
sleep 5

# Force Flux to recreate PVCs
echo "Reconciling Flux to recreate PVCs..."
flux reconcile kustomization flux-system --with-source

# Wait for PVCs to be recreated
echo "Waiting for PVCs to be created..."
for i in {1..30}; do
    if kubectl get pvc frigate-config frigate-media -n frigate &>/dev/null; then
        echo "PVCs created."
        break
    fi
    echo "Attempt $i/30 - waiting 2s..."
    sleep 2
done

# Show PVC status
echo ""
echo "=== PVC Status ==="
kubectl get pvc -n frigate

echo ""
echo "Done. PVCs recreated for still-fawn."
