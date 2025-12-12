#!/bin/bash
#
# 19-switch-to-onnx-detector.sh
#
# Switch Frigate from CPU detector to ONNX GPU detector.
# Prerequisite: Run build-onnx-k8s-job.sh first to build the model.
#

set -euo pipefail

KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"
NAMESPACE="frigate"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo "========================================="
echo "Switch Frigate to ONNX GPU Detector"
echo "========================================="
echo ""

# Step 1: Verify model exists
echo "Step 1: Verifying ONNX model exists..."
MODEL_PATH="/config/yolov9-c-640.onnx"
if ! KUBECONFIG="$KUBECONFIG" kubectl exec -n "$NAMESPACE" deployment/frigate -- ls -lh "$MODEL_PATH" 2>/dev/null; then
    echo -e "${RED}ERROR: Model not found at $MODEL_PATH${NC}"
    echo "Run build-onnx-k8s-job.sh first to build the model."
    exit 1
fi
echo ""

# Step 2: Fix configmap model path if needed
echo "Step 2: Updating configmap with correct model path..."
CONFIGMAP_FILE="/Users/10381054/code/home/k8s/frigate-016/configmap-onnx.yaml"

# Update path from /config/models/... to /config/...
sed -i '' 's|path: /config/models/yolov9-c-640.onnx|path: /config/yolov9-c-640.onnx|g' "$CONFIGMAP_FILE"
echo "  Updated: model path set to /config/yolov9-c-640.onnx"
echo ""

# Step 3: Get current detector stats
echo "Step 3: Current detector stats (before switch)..."
KUBECONFIG="$KUBECONFIG" kubectl exec -n "$NAMESPACE" deployment/frigate -- \
    curl -s http://localhost:5000/api/stats | jq '.detectors'
echo ""

# Step 4: Apply ONNX configmap
echo "Step 4: Applying ONNX configmap..."
KUBECONFIG="$KUBECONFIG" kubectl apply -f "$CONFIGMAP_FILE"
echo ""

# Step 5: Restart Frigate
echo "Step 5: Restarting Frigate deployment..."
KUBECONFIG="$KUBECONFIG" kubectl rollout restart deployment/frigate -n "$NAMESPACE"
KUBECONFIG="$KUBECONFIG" kubectl rollout status deployment/frigate -n "$NAMESPACE" --timeout=180s
echo ""

# Step 6: Wait for Frigate to be ready
echo "Step 6: Waiting for Frigate to initialize (30s)..."
sleep 30
echo ""

# Step 7: Verify new detector
echo "Step 7: New detector stats (after switch)..."
KUBECONFIG="$KUBECONFIG" kubectl exec -n "$NAMESPACE" deployment/frigate -- \
    curl -s http://localhost:5000/api/stats | jq '.detectors'
echo ""

# Step 8: Check CPU usage
echo "Step 8: Checking pod CPU usage..."
KUBECONFIG="$KUBECONFIG" kubectl top pod -n "$NAMESPACE" -l app=frigate
echo ""

echo "========================================="
echo -e "${GREEN}Switched to ONNX GPU detector!${NC}"
echo "========================================="
echo ""
echo "Expected changes:"
echo "  - CPU usage: ~2100m → ~500m"
echo "  - Inference: ~13ms → <5ms"
echo "  - Detector type: cpu → onnx"
echo ""
echo "Rollback if needed:"
echo "  kubectl apply -f k8s/frigate-016/configmap.yaml"
echo "  kubectl rollout restart deployment/frigate -n frigate"
