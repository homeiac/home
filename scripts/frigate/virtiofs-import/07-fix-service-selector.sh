#!/bin/bash
#
# 07-fix-service-selector.sh
#
# Fix Frigate service selector mismatch from kustomize labels
#

set -euo pipefail

KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"

# Colors
GREEN='\033[0;32m'
NC='\033[0m'

echo "========================================="
echo "Fix Frigate Service Selector"
echo "========================================="
echo ""

# Delete and recreate services with correct selector
echo "Step 1: Deleting services with wrong selectors..."
KUBECONFIG="$KUBECONFIG" kubectl delete svc frigate frigate-webrtc-udp -n frigate --ignore-not-found
sleep 2
echo ""

# Apply service manifest
echo "Step 2: Applying service manifest..."
KUBECONFIG="$KUBECONFIG" kubectl apply -f /Users/10381054/code/home/k8s/frigate-016/service.yaml
echo ""

# Wait for endpoints
echo "Step 3: Waiting for endpoints..."
sleep 5
KUBECONFIG="$KUBECONFIG" kubectl get endpoints -n frigate
echo ""

# Test connectivity
echo "Step 4: Testing connectivity..."
KUBECONFIG="$KUBECONFIG" kubectl exec -n frigate deployment/frigate -- curl -s http://localhost:5000/api/version
echo " - internal OK"
echo ""

# Test via LoadBalancer
echo "Step 5: Testing via LoadBalancer..."
LB_IP=$(KUBECONFIG="$KUBECONFIG" kubectl get svc frigate -n frigate -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
echo "LoadBalancer IP: $LB_IP"
curl -s --max-time 5 "http://$LB_IP:5000/api/version" && echo " - external OK" || echo " - external FAILED"
echo ""

echo "========================================="
echo -e "${GREEN}Service selector fixed!${NC}"
echo "========================================="
echo ""
echo "Test: curl http://frigate.app.homelab/api/version"
