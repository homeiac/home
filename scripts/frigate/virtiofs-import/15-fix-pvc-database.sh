#!/bin/bash
#
# 15-fix-pvc-database.sh
#
# Fix the Frigate database in the PVC by copying via nsenter into the node.
#

set -euo pipefail

KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"
NAMESPACE="frigate"
PVC_PATH="/var/lib/rancher/k3s/storage/pvc-d5e5afb8-6446-4128-96c1-1eba3084347f_frigate_frigate-config"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "========================================="
echo "Fix Frigate Database in PVC"
echo "========================================="
echo ""

# Step 1: Verify local merged database
echo "Step 1: Verifying local merged database..."
if [ ! -f /tmp/frigate-merged.db ]; then
    echo "ERROR: /tmp/frigate-merged.db not found"
    exit 1
fi
sqlite3 /tmp/frigate-merged.db "PRAGMA integrity_check"
sqlite3 /tmp/frigate-merged.db "SELECT 'recordings:', COUNT(*) FROM recordings; SELECT 'reviewsegment:', COUNT(*) FROM reviewsegment; SELECT 'event:', COUNT(*) FROM event"
echo ""

# Step 2: Scale down Frigate deployment
echo "Step 2: Scaling down Frigate deployment..."
KUBECONFIG="$KUBECONFIG" kubectl scale deployment frigate -n "$NAMESPACE" --replicas=0
sleep 3
KUBECONFIG="$KUBECONFIG" kubectl wait --for=delete pod -l app=frigate -n "$NAMESPACE" --timeout=60s 2>/dev/null || true
echo ""

# Step 3: Create a privileged pod to access the host filesystem
echo "Step 3: Creating privileged pod for host access..."
KUBECONFIG="$KUBECONFIG" kubectl apply -f - << 'EOF'
apiVersion: v1
kind: Pod
metadata:
  name: db-fixer
  namespace: frigate
spec:
  nodeName: k3s-vm-pumped-piglet-gpu
  hostPID: true
  containers:
  - name: fixer
    image: ubuntu:24.04
    command: ["sleep", "3600"]
    securityContext:
      privileged: true
    volumeMounts:
    - name: host
      mountPath: /host
  volumes:
  - name: host
    hostPath:
      path: /
  restartPolicy: Never
EOF

echo "  Waiting for pod..."
KUBECONFIG="$KUBECONFIG" kubectl wait --for=condition=Ready pod/db-fixer -n "$NAMESPACE" --timeout=60s
echo ""

# Step 4: Copy database into pod then to host path
echo "Step 4: Copying database to PVC via privileged pod..."
KUBECONFIG="$KUBECONFIG" kubectl cp /tmp/frigate-merged.db "$NAMESPACE/db-fixer:/tmp/frigate.db"

# Verify the copy worked
KUBECONFIG="$KUBECONFIG" kubectl exec -n "$NAMESPACE" db-fixer -- ls -la /tmp/frigate.db

# Copy to host path using nsenter
KUBECONFIG="$KUBECONFIG" kubectl exec -n "$NAMESPACE" db-fixer -- cp /tmp/frigate.db "/host$PVC_PATH/frigate.db"
KUBECONFIG="$KUBECONFIG" kubectl exec -n "$NAMESPACE" db-fixer -- ls -la "/host$PVC_PATH/frigate.db"
echo ""

# Step 5: Verify database integrity on host
echo "Step 5: Verifying database on host..."
KUBECONFIG="$KUBECONFIG" kubectl exec -n "$NAMESPACE" db-fixer -- apt-get update -qq
KUBECONFIG="$KUBECONFIG" kubectl exec -n "$NAMESPACE" db-fixer -- apt-get install -y -qq sqlite3
KUBECONFIG="$KUBECONFIG" kubectl exec -n "$NAMESPACE" db-fixer -- sqlite3 "/host$PVC_PATH/frigate.db" "PRAGMA integrity_check; SELECT 'recordings:', COUNT(*) FROM recordings; SELECT 'reviewsegment:', COUNT(*) FROM reviewsegment"
echo ""

# Step 6: Cleanup privileged pod
echo "Step 6: Cleaning up privileged pod..."
KUBECONFIG="$KUBECONFIG" kubectl delete pod db-fixer -n "$NAMESPACE" --force --grace-period=0
echo ""

# Step 7: Scale Frigate back up
echo "Step 7: Scaling Frigate back up..."
KUBECONFIG="$KUBECONFIG" kubectl scale deployment frigate -n "$NAMESPACE" --replicas=1
echo "  Waiting for pod to be ready..."
KUBECONFIG="$KUBECONFIG" kubectl wait --for=condition=Ready pod -l app=frigate -n "$NAMESPACE" --timeout=180s
echo ""

# Step 8: Verify in Frigate pod
echo "Step 8: Verifying database in Frigate pod..."
POD=$(KUBECONFIG="$KUBECONFIG" kubectl get pods -n "$NAMESPACE" -l app=frigate -o jsonpath='{.items[0].metadata.name}')
KUBECONFIG="$KUBECONFIG" kubectl exec -n "$NAMESPACE" "$POD" -- python3 -c "
import sqlite3
conn = sqlite3.connect('/config/frigate.db')
print('Integrity:', conn.execute('PRAGMA integrity_check').fetchone()[0])
for t in ['recordings', 'reviewsegment', 'event']:
    c = conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
    print(f'{t}: {c}')
"
echo ""

# Step 9: Cleanup temp container on Proxmox
echo "Step 9: Cleaning up temp container..."
ssh root@pumped-piglet.maas "pct destroy 9113 --force 2>/dev/null || true; rm -f /tmp/frigate-merged.db /tmp/frigate-old.db"
echo ""

echo "========================================="
echo -e "${GREEN}Database fixed!${NC}"
echo "========================================="
echo ""
echo "Check: http://frigate.app.homelab/review"
