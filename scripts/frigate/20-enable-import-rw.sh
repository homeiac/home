#!/bin/bash
# 20-enable-import-rw.sh - Enable read-write on /import mount for Frigate cleanup
#
# Problem: Frigate recording_cleanup thread crashes because /import is read-only
# Solution: Change volumeMount readOnly from true to false
#
# This allows Frigate to delete old recordings and manage storage properly

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOYMENT_FILE="${SCRIPT_DIR}/../../k8s/frigate-016/deployment.yaml"
KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"

echo "========================================="
echo "Enable Read-Write on Frigate /import Mount"
echo "========================================="
echo ""

# Step 1: Check current mount status
echo "Step 1: Checking current mount status..."
CURRENT_MOUNT=$(KUBECONFIG=$KUBECONFIG kubectl exec -n frigate deployment/frigate -- mount | grep import || true)
echo "  Current: $CURRENT_MOUNT"
echo ""

# Step 2: Check current I/O
echo "Step 2: Current I/O stats (baseline)..."
ssh root@pumped-piglet.maas "zpool iostat local-20TB-zfs 1 1" 2>/dev/null | tail -2
echo ""

# Step 3: Update deployment file
echo "Step 3: Updating deployment file..."
if grep -q "readOnly: true" "$DEPLOYMENT_FILE"; then
    sed -i '' 's/readOnly: true/readOnly: false/' "$DEPLOYMENT_FILE"
    echo "  Updated: readOnly changed from true to false"
else
    echo "  Already set to readOnly: false or not found"
fi
echo ""

# Step 4: Apply deployment
echo "Step 4: Applying updated deployment..."
KUBECONFIG=$KUBECONFIG kubectl apply -f "$DEPLOYMENT_FILE"
echo ""

# Step 5: Wait for rollout
echo "Step 5: Waiting for rollout to complete..."
KUBECONFIG=$KUBECONFIG kubectl rollout status deployment/frigate -n frigate --timeout=120s
echo ""

# Step 6: Verify mount is now rw
echo "Step 6: Verifying mount is read-write..."
sleep 10
NEW_MOUNT=$(KUBECONFIG=$KUBECONFIG kubectl exec -n frigate deployment/frigate -- mount | grep import || true)
echo "  New: $NEW_MOUNT"
echo ""

# Step 7: Check for cleanup errors
echo "Step 7: Checking for cleanup errors (wait 30s for cleanup to run)..."
sleep 30
ERRORS=$(KUBECONFIG=$KUBECONFIG kubectl logs -n frigate deployment/frigate --tail=50 2>/dev/null | grep -i "read-only" || echo "None found")
echo "  Errors: $ERRORS"
echo ""

# Step 8: Check I/O after fix
echo "Step 8: Checking I/O after fix..."
ssh root@pumped-piglet.maas "zpool iostat local-20TB-zfs 2 3" 2>/dev/null | tail -4
echo ""

# Step 9: Check load average
echo "Step 9: Checking host load average..."
ssh root@pumped-piglet.maas "uptime" 2>/dev/null
echo ""

echo "========================================="
echo "Done! Check if I/O dropped and load decreased."
echo "========================================="
