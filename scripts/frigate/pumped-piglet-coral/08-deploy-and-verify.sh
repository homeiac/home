#!/bin/bash
# 08-deploy-and-verify.sh - Deploy Frigate with Coral TPU and verify

set -e

MANIFEST_DIR="/Users/10381054/code/home/k8s/frigate-016"
export KUBECONFIG=~/kubeconfig

echo "========================================="
echo "Step 8: Deploy Frigate with Coral TPU"
echo "========================================="
echo ""

# Show what we're deploying
echo "Deployment changes:"
echo "  - Image: frigate:0.16.0 (regular, not tensorrt)"
echo "  - Detector: Coral EdgeTPU USB"
echo "  - Node: k3s-vm-pumped-piglet-gpu"
echo ""

# Apply manifests
echo "Applying configmap..."
kubectl apply -f "$MANIFEST_DIR/configmap.yaml"
echo ""

echo "Applying deployment..."
kubectl apply -f "$MANIFEST_DIR/deployment.yaml"
echo ""

# Restart deployment to pick up new config
echo "Restarting deployment..."
kubectl rollout restart deployment frigate -n frigate
echo ""

# Wait for rollout
echo "Waiting for rollout (timeout 5 minutes)..."
kubectl rollout status deployment frigate -n frigate --timeout=300s
echo ""

# Wait extra time for Frigate to initialize
echo "Waiting 30s for Frigate initialization..."
sleep 30
echo ""

# Verify deployment
echo "========================================="
echo "Verification:"
echo "========================================="
echo ""

echo "Pod status:"
kubectl get pods -n frigate -o wide
echo ""

echo "Pod logs (last 20 lines):"
kubectl logs -n frigate deployment/frigate --tail=20 2>&1 || echo "Logs not available yet"
echo ""

echo "Checking detector stats..."
POD=$(kubectl get pods -n frigate -l app=frigate -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [ -n "$POD" ]; then
  kubectl exec -n frigate $POD -- curl -s http://localhost:5000/api/stats 2>/dev/null | jq '.detectors' || echo "Stats not available yet"
fi
echo ""

echo "========================================="
echo "Deployment complete. Check detector stats above."
echo "Expected: type: edgetpu, inference_speed: ~10ms"
echo "========================================="
