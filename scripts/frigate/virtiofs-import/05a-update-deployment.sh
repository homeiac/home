#!/bin/bash
#
# 05a-update-deployment.sh
#
# Update Frigate deployment hostPath to point to frigate subdirectory
#

set -euo pipefail

KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"
DEPLOYMENT_FILE="/Users/10381054/code/home/k8s/frigate-016/deployment.yaml"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "========================================="
echo "Update Frigate Deployment hostPath"
echo "========================================="
echo ""

# Update the hostPath
echo "Step 1: Updating deployment.yaml..."
sed -i '' 's|path: /mnt/frigate-import$|path: /mnt/frigate-import/frigate|' "$DEPLOYMENT_FILE"
echo -e "${GREEN}Updated hostPath to /mnt/frigate-import/frigate${NC}"
echo ""

# Show the change
echo "Step 2: Verifying change..."
grep -A2 "old-recordings" "$DEPLOYMENT_FILE"
echo ""

# Update comment
sed -i '' 's|# Old Frigate recordings via 9p mount from host|# Old Frigate recordings via virtiofs from host|' "$DEPLOYMENT_FILE"
echo ""

# Apply the deployment
echo "Step 3: Applying deployment..."
KUBECONFIG="$KUBECONFIG" kubectl apply -f "$DEPLOYMENT_FILE"
echo ""

# Wait for rollout
echo "Step 4: Waiting for rollout..."
KUBECONFIG="$KUBECONFIG" kubectl rollout status deployment/frigate -n frigate --timeout=120s
echo -e "${GREEN}Rollout complete${NC}"
echo ""

echo "========================================="
echo -e "${GREEN}Deployment updated!${NC}"
echo "========================================="
echo ""
echo "Next: Run 06-verify-frigate-access.sh"
