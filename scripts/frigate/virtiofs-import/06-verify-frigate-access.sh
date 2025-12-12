#!/bin/bash
#
# 06-verify-frigate-access.sh
#
# Verify Frigate pod can access old recordings via virtiofs mount
#

set -euo pipefail

KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"
NAMESPACE="frigate"
DEPLOYMENT="frigate"
IMPORT_PATH="/import"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "========================================="
echo "Verify Frigate Access to Old Recordings"
echo "========================================="
echo ""

# Check K3s cluster health
echo "Step 1: Checking K3s cluster health..."
KUBECONFIG="$KUBECONFIG" kubectl get nodes -o wide
echo ""

NODE_COUNT=$(KUBECONFIG="$KUBECONFIG" kubectl get nodes --no-headers | grep -c "Ready")
if [ "$NODE_COUNT" -lt 3 ]; then
    echo -e "${YELLOW}Warning: Only $NODE_COUNT/3 nodes Ready${NC}"
fi
echo ""

# Check Frigate deployment
echo "Step 2: Checking Frigate deployment..."
KUBECONFIG="$KUBECONFIG" kubectl get deployment -n $NAMESPACE $DEPLOYMENT
echo ""

# Check pod status
echo "Step 3: Checking Frigate pod..."
KUBECONFIG="$KUBECONFIG" kubectl get pods -n $NAMESPACE -l app=frigate -o wide
echo ""

POD_STATUS=$(KUBECONFIG="$KUBECONFIG" kubectl get pods -n $NAMESPACE -l app=frigate --no-headers | awk '{print $3}')
if [ "$POD_STATUS" != "Running" ]; then
    echo -e "${YELLOW}Pod not running, restarting deployment...${NC}"
    KUBECONFIG="$KUBECONFIG" kubectl rollout restart deployment/$DEPLOYMENT -n $NAMESPACE
    echo "Waiting for rollout..."
    KUBECONFIG="$KUBECONFIG" kubectl rollout status deployment/$DEPLOYMENT -n $NAMESPACE --timeout=120s
    echo ""
fi

# Check import mount
echo "Step 4: Checking import mount in pod..."
POD_NAME=$(KUBECONFIG="$KUBECONFIG" kubectl get pods -n $NAMESPACE -l app=frigate -o jsonpath='{.items[0].metadata.name}')
echo "Pod: $POD_NAME"
echo ""

echo "Checking $IMPORT_PATH..."
if KUBECONFIG="$KUBECONFIG" kubectl exec -n $NAMESPACE $POD_NAME -- ls -la $IMPORT_PATH 2>/dev/null; then
    echo -e "${GREEN}Import path accessible${NC}"
else
    echo -e "${RED}Cannot access $IMPORT_PATH${NC}"
    echo ""
    echo "Checking mount points in pod:"
    KUBECONFIG="$KUBECONFIG" kubectl exec -n $NAMESPACE $POD_NAME -- mount | grep -E "frigate|import" || echo "No relevant mounts found"
    exit 1
fi
echo ""

# Check recordings
echo "Step 5: Checking for old recordings..."
if KUBECONFIG="$KUBECONFIG" kubectl exec -n $NAMESPACE $POD_NAME -- ls $IMPORT_PATH/recordings 2>/dev/null; then
    echo -e "${GREEN}Found recordings directory${NC}"
    echo ""
    echo "Recording folders:"
    KUBECONFIG="$KUBECONFIG" kubectl exec -n $NAMESPACE $POD_NAME -- ls $IMPORT_PATH/recordings | head -10
    echo ""
    echo "Size:"
    KUBECONFIG="$KUBECONFIG" kubectl exec -n $NAMESPACE $POD_NAME -- du -sh $IMPORT_PATH/recordings 2>/dev/null || true
else
    echo -e "${YELLOW}No recordings directory at $IMPORT_PATH/recordings${NC}"
    echo "Contents of $IMPORT_PATH:"
    KUBECONFIG="$KUBECONFIG" kubectl exec -n $NAMESPACE $POD_NAME -- ls -la $IMPORT_PATH 2>/dev/null || true
fi
echo ""

# Check Frigate API
echo "Step 6: Checking Frigate API..."
API_VERSION=$(KUBECONFIG="$KUBECONFIG" kubectl exec -n $NAMESPACE $POD_NAME -- curl -s http://localhost:5000/api/version 2>/dev/null || echo "FAILED")
if [ "$API_VERSION" != "FAILED" ]; then
    echo -e "${GREEN}Frigate API responding: $API_VERSION${NC}"
else
    echo -e "${RED}Frigate API not responding${NC}"
fi
echo ""

# Check Frigate service
echo "Step 7: Checking Frigate service endpoints..."
KUBECONFIG="$KUBECONFIG" kubectl get endpoints -n $NAMESPACE frigate
echo ""

echo "========================================="
echo -e "${GREEN}Verification complete!${NC}"
echo "========================================="
echo ""
echo "Summary:"
echo "  - K3s cluster: $NODE_COUNT/3 nodes Ready"
echo "  - Frigate pod: $POD_STATUS"
echo "  - Import path: $IMPORT_PATH accessible"
echo "  - API: $API_VERSION"
echo ""
echo "Access Frigate UI at: http://192.168.4.83:5000"
echo "Or via ingress: http://frigate.app.homelab"
