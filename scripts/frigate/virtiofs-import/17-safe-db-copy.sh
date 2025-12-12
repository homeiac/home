#!/bin/bash
#
# 17-safe-db-copy.sh
#
# Safely copy database to PVC using base64 encoding to avoid corruption.
#

set -euo pipefail

KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"
NAMESPACE="frigate"
PVC_PATH="/var/lib/rancher/k3s/storage/pvc-d5e5afb8-6446-4128-96c1-1eba3084347f_frigate_frigate-config"

# Colors
GREEN='\033[0;32m'
NC='\033[0m'

echo "========================================="
echo "Safe Database Copy"
echo "========================================="
echo ""

# Step 1: Verify source
echo "Step 1: Verifying source database..."
sqlite3 /tmp/frigate-clean.db "PRAGMA integrity_check"
sqlite3 /tmp/frigate-clean.db "SELECT 'reviewsegment:', COUNT(*) FROM reviewsegment"
ls -la /tmp/frigate-clean.db
echo ""

# Step 2: Scale down Frigate
echo "Step 2: Scaling down Frigate..."
KUBECONFIG="$KUBECONFIG" kubectl scale deployment frigate -n "$NAMESPACE" --replicas=0
sleep 5
KUBECONFIG="$KUBECONFIG" kubectl wait --for=delete pod -l app=frigate -n "$NAMESPACE" --timeout=60s 2>/dev/null || true
echo ""

# Step 3: Create helper pod with hostPath mount
echo "Step 3: Creating helper pod..."
KUBECONFIG="$KUBECONFIG" kubectl delete pod db-helper -n "$NAMESPACE" --force --grace-period=0 2>/dev/null || true
sleep 2

KUBECONFIG="$KUBECONFIG" kubectl apply -f - << EOF
apiVersion: v1
kind: Pod
metadata:
  name: db-helper
  namespace: frigate
spec:
  nodeName: k3s-vm-pumped-piglet-gpu
  containers:
  - name: helper
    image: ubuntu:24.04
    command: ["sleep", "3600"]
    volumeMounts:
    - name: pvc
      mountPath: /pvc
  volumes:
  - name: pvc
    hostPath:
      path: $PVC_PATH
  restartPolicy: Never
EOF

KUBECONFIG="$KUBECONFIG" kubectl wait --for=condition=Ready pod/db-helper -n "$NAMESPACE" --timeout=60s
echo ""

# Step 4: Encode and transfer
echo "Step 4: Encoding and transferring database..."
# Create base64 encoded file (macOS compatible)
base64 -i /tmp/frigate-clean.db -o /tmp/frigate-clean.db.b64
ls -la /tmp/frigate-clean.db.b64
echo ""

# Copy the base64 file to pod
KUBECONFIG="$KUBECONFIG" kubectl cp /tmp/frigate-clean.db.b64 "$NAMESPACE/db-helper:/tmp/frigate.db.b64"

# Decode in pod and write to PVC
KUBECONFIG="$KUBECONFIG" kubectl exec -n "$NAMESPACE" db-helper -- bash -c 'base64 -d /tmp/frigate.db.b64 > /pvc/frigate.db'
echo ""

# Step 5: Verify in pod
echo "Step 5: Verifying in pod..."
KUBECONFIG="$KUBECONFIG" kubectl exec -n "$NAMESPACE" db-helper -- ls -la /pvc/frigate.db
KUBECONFIG="$KUBECONFIG" kubectl exec -n "$NAMESPACE" db-helper -- apt-get update -qq 2>/dev/null
KUBECONFIG="$KUBECONFIG" kubectl exec -n "$NAMESPACE" db-helper -- apt-get install -y -qq sqlite3 2>/dev/null
KUBECONFIG="$KUBECONFIG" kubectl exec -n "$NAMESPACE" db-helper -- sqlite3 /pvc/frigate.db "PRAGMA integrity_check; SELECT 'reviewsegment:', COUNT(*) FROM reviewsegment"
echo ""

# Step 6: Cleanup helper
echo "Step 6: Cleanup..."
KUBECONFIG="$KUBECONFIG" kubectl delete pod db-helper -n "$NAMESPACE" --force --grace-period=0
rm -f /tmp/frigate-clean.db.b64
echo ""

# Step 7: Start Frigate
echo "Step 7: Starting Frigate..."
KUBECONFIG="$KUBECONFIG" kubectl scale deployment frigate -n "$NAMESPACE" --replicas=1
KUBECONFIG="$KUBECONFIG" kubectl wait --for=condition=Ready pod -l app=frigate -n "$NAMESPACE" --timeout=180s
echo ""

# Step 8: Verify
echo "Step 8: Final verification..."
POD=$(KUBECONFIG="$KUBECONFIG" kubectl get pods -n "$NAMESPACE" -l app=frigate -o jsonpath='{.items[0].metadata.name}')
sleep 5
KUBECONFIG="$KUBECONFIG" kubectl exec -n "$NAMESPACE" "$POD" -- python3 -c "
import sqlite3
conn = sqlite3.connect('/config/frigate.db')
print('Integrity:', conn.execute('PRAGMA integrity_check').fetchone()[0])
for t in ['recordings', 'reviewsegment', 'event']:
    c = conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
    print(f'{t}: {c}')
"
echo ""

echo "========================================="
echo -e "${GREEN}Database copied successfully!${NC}"
echo "========================================="
echo ""
echo "Check: http://frigate.app.homelab/review"
