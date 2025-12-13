#!/bin/bash
# 21-remove-virtiofs-mount.sh - Remove VirtioFS mount and reset Frigate database
#
# Problem: VirtioFS mount to USB drive causes 12MB/s constant I/O and 15+ load
# Solution: Remove VirtioFS mount, start fresh with local VM storage
#
# This script:
# 1. Backs up current database
# 2. Removes VirtioFS volumeMount and volume from deployment
# 3. Deletes database (fresh start)
# 4. Applies deployment and restarts Frigate
# 5. Verifies I/O dropped

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOYMENT_FILE="${SCRIPT_DIR}/../../k8s/frigate-016/deployment.yaml"
KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"

echo "========================================="
echo "Remove VirtioFS Mount + Fresh Database"
echo "========================================="
echo ""
echo "This will:"
echo "  - Remove /import VirtioFS mount from deployment"
echo "  - Delete frigate.db (fresh start)"
echo "  - All old recording history will be lost"
echo ""

# Step 1: Pre-flight checks
echo "Step 1: Pre-flight checks..."
echo "  Current I/O baseline:"
ssh root@pumped-piglet.maas "zpool iostat local-20TB-zfs 1 1" 2>/dev/null | tail -1
echo "  Current load:"
ssh root@pumped-piglet.maas "uptime" 2>/dev/null | grep -o 'load average:.*'
echo ""

# Step 2: Backup database
echo "Step 2: Backing up current database..."
KUBECONFIG=$KUBECONFIG kubectl exec -n frigate deployment/frigate -- \
  cp /config/frigate.db /config/frigate.db.pre-reset-backup 2>/dev/null || echo "  No existing DB to backup"
echo "  Backup: /config/frigate.db.pre-reset-backup"
echo ""

# Step 3: Remove VirtioFS volumeMount from deployment
echo "Step 3: Removing VirtioFS volumeMount from deployment..."
if grep -q "name: old-recordings" "$DEPLOYMENT_FILE"; then
    # Remove the volumeMount block (lines with old-recordings mount)
    sed -i '' '/# Old Frigate recordings for import/,/readOnly:/d' "$DEPLOYMENT_FILE"
    echo "  Removed volumeMount"
else
    echo "  volumeMount already removed"
fi

# Step 4: Remove VirtioFS volume from deployment
echo "Step 4: Removing VirtioFS volume from deployment..."
if grep -q "path: /mnt/frigate-import" "$DEPLOYMENT_FILE"; then
    # Remove the volume block
    sed -i '' '/# Old Frigate recordings via virtiofs/,/type: Directory/d' "$DEPLOYMENT_FILE"
    echo "  Removed volume"
else
    echo "  volume already removed"
fi
echo ""

# Step 5: Delete database
echo "Step 5: Deleting database for fresh start..."
KUBECONFIG=$KUBECONFIG kubectl exec -n frigate deployment/frigate -- \
  rm -f /config/frigate.db 2>/dev/null || true
echo "  Database deleted"
echo ""

# Step 6: Apply deployment
echo "Step 6: Applying updated deployment..."
KUBECONFIG=$KUBECONFIG kubectl apply -f "$DEPLOYMENT_FILE"
echo ""

# Step 7: Restart Frigate
echo "Step 7: Restarting Frigate..."
KUBECONFIG=$KUBECONFIG kubectl rollout restart deployment/frigate -n frigate
KUBECONFIG=$KUBECONFIG kubectl rollout status deployment/frigate -n frigate --timeout=120s
echo ""

# Step 8: Wait for Frigate to initialize
echo "Step 8: Waiting for Frigate to initialize (30s)..."
sleep 30
echo ""

# Step 9: Verify no /import mount
echo "Step 9: Verifying /import mount removed..."
IMPORT_MOUNT=$(KUBECONFIG=$KUBECONFIG kubectl exec -n frigate deployment/frigate -- mount 2>/dev/null | grep import || echo "None")
echo "  Import mount: $IMPORT_MOUNT"
echo ""

# Step 10: Check I/O
echo "Step 10: Checking I/O after fix..."
ssh root@pumped-piglet.maas "zpool iostat local-20TB-zfs 3 3" 2>/dev/null | tail -4
echo ""

# Step 11: Check load
echo "Step 11: Checking host load..."
ssh root@pumped-piglet.maas "uptime" 2>/dev/null
echo ""

# Step 12: Check Frigate status
echo "Step 12: Checking Frigate status..."
KUBECONFIG=$KUBECONFIG kubectl exec -n frigate deployment/frigate -- \
  curl -s http://localhost:5000/api/stats 2>/dev/null | jq '{detectors: .detectors, detection_fps: .detection_fps}' || echo "  API not ready yet"
echo ""

# Step 13: Check recordings
echo "Step 13: Checking recordings directory..."
KUBECONFIG=$KUBECONFIG kubectl exec -n frigate deployment/frigate -- \
  ls -la /media/frigate/recordings/ 2>/dev/null || echo "  Empty or not accessible"
echo ""

echo "========================================="
echo "Done! VirtioFS removed, fresh database created."
echo "========================================="
echo ""
echo "Expected results:"
echo "  - I/O on local-20TB-zfs should drop to near 0"
echo "  - Load average should drop from 15+ to <5"
echo "  - Recordings will start fresh from now"
