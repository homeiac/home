#!/bin/bash
#
# add-storage-mount.sh
#
# Add hostPath mount for old Frigate recordings to K8s deployment
# Mounts /local-3TB-backup/subvol-113-disk-0 as read-only for import
#

set -euo pipefail

DEPLOYMENT_FILE="/Users/10381054/code/home/k8s/frigate-016/deployment.yaml"
KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "========================================="
echo "Add Storage Mount to Frigate Deployment"
echo "========================================="
echo ""

# Step 1: Check if mount already exists
echo "Step 1: Checking if mount already exists..."
if grep -q "old-recordings" "$DEPLOYMENT_FILE"; then
    echo -e "${YELLOW}Mount 'old-recordings' already exists in deployment${NC}"
    echo "Skipping modification."
else
    echo "Adding old-recordings mount to deployment..."

    # Add volumeMount after the dri mount
    sed -i '' '/mountPath: \/dev\/dri/a\
            # Old Frigate recordings for import (read-only)\
            - name: old-recordings\
              mountPath: /import\
              readOnly: true
' "$DEPLOYMENT_FILE"

    # Add volume after the dri volume
    sed -i '' '/path: \/dev\/dri/a\
        # Old Frigate recordings from LXC 113\
        - name: old-recordings\
          hostPath:\
            path: /local-3TB-backup/subvol-113-disk-0\
            type: Directory
' "$DEPLOYMENT_FILE"

    echo -e "${GREEN}✓ Added old-recordings mount to deployment.yaml${NC}"
fi
echo ""

# Step 2: Show the changes
echo "Step 2: Showing volume configuration..."
echo ""
grep -A 2 "old-recordings" "$DEPLOYMENT_FILE" || echo "No old-recordings found"
echo ""

# Step 3: Apply the deployment
echo "Step 3: Applying updated deployment..."
KUBECONFIG="$KUBECONFIG" kubectl apply -f "$DEPLOYMENT_FILE"
echo ""

# Step 4: Wait for rollout
echo "Step 4: Waiting for rollout..."
KUBECONFIG="$KUBECONFIG" kubectl rollout status deployment/frigate -n frigate --timeout=120s
echo ""

# Step 5: Verify mount
echo "Step 5: Verifying mount in pod..."
sleep 5
POD=$(KUBECONFIG="$KUBECONFIG" kubectl get pod -n frigate -l app=frigate -o jsonpath='{.items[0].metadata.name}')
echo "Pod: $POD"
KUBECONFIG="$KUBECONFIG" kubectl exec -n frigate "$POD" -- ls -la /import/ 2>/dev/null | head -20 || echo "Mount not accessible yet"
echo ""

echo "========================================="
echo -e "${GREEN}Storage mount added!${NC}"
echo "========================================="
echo ""
echo "Old recordings available at: /import/"
echo "To import recordings, copy from /import/frigate/ to /media/frigate/"
