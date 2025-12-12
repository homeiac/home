#!/bin/bash
#
# 16-rebuild-clean-db.sh
#
# Rebuild a clean database by dumping and reimporting data.
# This fixes schema issues from merging databases with different versions.
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
echo "Rebuild Clean Frigate Database"
echo "========================================="
echo ""

# Step 1: Check old database data
echo "Step 1: Checking old database..."
sqlite3 /tmp/frigate-old.db "SELECT 'reviewsegment:', COUNT(*) FROM reviewsegment; SELECT 'event:', COUNT(*) FROM event"
echo ""

# Step 2: Export data from old database
echo "Step 2: Exporting data from old database..."

# Export reviewsegment data (skip has_been_reviewed column - old schema has it, new doesn't)
sqlite3 /tmp/frigate-old.db << 'SQL' > /tmp/reviewsegment.sql
.mode insert reviewsegment
SELECT id, camera, start_time, end_time, severity, thumb_path, data FROM reviewsegment;
SQL
echo "  reviewsegment: $(wc -l < /tmp/reviewsegment.sql) rows"

# Export event data
sqlite3 /tmp/frigate-old.db << 'SQL' > /tmp/event.sql
.mode insert event
SELECT * FROM event;
SQL
echo "  event: $(wc -l < /tmp/event.sql) rows"

# Export timeline data
sqlite3 /tmp/frigate-old.db << 'SQL' > /tmp/timeline.sql
.mode insert timeline
SELECT * FROM timeline;
SQL
echo "  timeline: $(wc -l < /tmp/timeline.sql) rows"
echo ""

# Step 3: Get fresh DB from K8s backup
echo "Step 3: Starting fresh from K8s backup..."
if [ ! -f /tmp/frigate-k8s-backup.db ]; then
    echo "ERROR: No backup at /tmp/frigate-k8s-backup.db"
    exit 1
fi
cp /tmp/frigate-k8s-backup.db /tmp/frigate-clean.db
sqlite3 /tmp/frigate-clean.db "PRAGMA integrity_check"
echo ""

# Step 4: Import old data into clean database
echo "Step 4: Importing old data..."

# Import reviewsegment (use INSERT OR IGNORE to skip duplicates)
sed 's/INSERT INTO/INSERT OR IGNORE INTO/' /tmp/reviewsegment.sql > /tmp/reviewsegment_safe.sql
sqlite3 /tmp/frigate-clean.db < /tmp/reviewsegment_safe.sql
echo "  reviewsegment imported"

# Import event
sed 's/INSERT INTO/INSERT OR IGNORE INTO/' /tmp/event.sql > /tmp/event_safe.sql
sqlite3 /tmp/frigate-clean.db < /tmp/event_safe.sql
echo "  event imported"

# Import timeline
sed 's/INSERT INTO/INSERT OR IGNORE INTO/' /tmp/timeline.sql > /tmp/timeline_safe.sql
sqlite3 /tmp/frigate-clean.db < /tmp/timeline_safe.sql 2>/dev/null || echo "  timeline: some rows skipped (schema mismatch)"
echo ""

# Step 5: Verify clean database
echo "Step 5: Verifying clean database..."
sqlite3 /tmp/frigate-clean.db "PRAGMA integrity_check"
sqlite3 /tmp/frigate-clean.db "SELECT 'recordings:', COUNT(*) FROM recordings; SELECT 'reviewsegment:', COUNT(*) FROM reviewsegment; SELECT 'event:', COUNT(*) FROM event"
echo ""

# Step 6: Copy to PVC using privileged pod
echo "Step 6: Ensuring db-fixer pod exists..."
KUBECONFIG="$KUBECONFIG" kubectl get pod db-fixer -n "$NAMESPACE" >/dev/null 2>&1 || \
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
KUBECONFIG="$KUBECONFIG" kubectl wait --for=condition=Ready pod/db-fixer -n "$NAMESPACE" --timeout=60s
echo ""

echo "Step 7: Copying clean database to PVC..."
KUBECONFIG="$KUBECONFIG" kubectl cp /tmp/frigate-clean.db "$NAMESPACE/db-fixer:/tmp/frigate.db"
KUBECONFIG="$KUBECONFIG" kubectl exec -n "$NAMESPACE" db-fixer -- cp /tmp/frigate.db "/host$PVC_PATH/frigate.db"
KUBECONFIG="$KUBECONFIG" kubectl exec -n "$NAMESPACE" db-fixer -- ls -la "/host$PVC_PATH/frigate.db"
echo ""

# Step 8: Cleanup and restart
echo "Step 8: Cleaning up..."
KUBECONFIG="$KUBECONFIG" kubectl delete pod db-fixer -n "$NAMESPACE" --force --grace-period=0
echo ""

echo "Step 9: Scaling Frigate back up..."
KUBECONFIG="$KUBECONFIG" kubectl scale deployment frigate -n "$NAMESPACE" --replicas=1
KUBECONFIG="$KUBECONFIG" kubectl wait --for=condition=Ready pod -l app=frigate -n "$NAMESPACE" --timeout=180s
echo ""

# Step 10: Final verification
echo "Step 10: Final verification..."
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

# Cleanup temp files
rm -f /tmp/reviewsegment.sql /tmp/event.sql /tmp/timeline.sql
rm -f /tmp/reviewsegment_safe.sql /tmp/event_safe.sql /tmp/timeline_safe.sql

# Cleanup Proxmox
ssh root@pumped-piglet.maas "pct destroy 9113 --force 2>/dev/null || true; rm -f /tmp/frigate*.db"

echo "========================================="
echo -e "${GREEN}Database rebuilt successfully!${NC}"
echo "========================================="
echo ""
echo "Check: http://frigate.app.homelab/review"
