#!/bin/bash
#
# 14-fix-db-corruption.sh
#
# Fix database corruption by restoring backup and properly merging.
# Uses sqlite3 dump/import instead of kubectl cp to avoid corruption.
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
echo "Fix Frigate Database Corruption"
echo "========================================="
echo ""

# Step 1: Check if we have backup
echo "Step 1: Checking backup..."
if [ ! -f /tmp/frigate-k8s-backup.db ]; then
    echo -e "${RED}ERROR: No backup found at /tmp/frigate-k8s-backup.db${NC}"
    exit 1
fi
ls -la /tmp/frigate-k8s-backup.db
echo ""

# Step 2: Verify backup integrity
echo "Step 2: Verifying backup integrity..."
sqlite3 /tmp/frigate-k8s-backup.db "PRAGMA integrity_check"
echo ""

# Step 3: Verify merged DB integrity
echo "Step 3: Checking merged database..."
if [ -f /tmp/frigate-merged.db ]; then
    if sqlite3 /tmp/frigate-merged.db "PRAGMA integrity_check" 2>/dev/null | grep -q "ok"; then
        echo "  Merged DB is intact"
        USE_MERGED=true
    else
        echo "  Merged DB is corrupted, will rebuild"
        USE_MERGED=false
    fi
else
    echo "  Merged DB not found, will rebuild"
    USE_MERGED=false
fi
echo ""

# Step 4: Rebuild merged database if needed
if [ "$USE_MERGED" = false ]; then
    echo "Step 4: Rebuilding merged database..."

    # Start fresh from backup
    cp /tmp/frigate-k8s-backup.db /tmp/frigate-merged.db

    # Merge using SQL ATTACH (safer than copying)
    python3 << 'PYTHON'
import sqlite3
import os

print("Attaching old database...")
conn = sqlite3.connect("/tmp/frigate-merged.db")
conn.execute("ATTACH DATABASE '/tmp/frigate-old.db' AS old")

# Import reviewsegment
print("Importing reviewsegment...")
cursor = conn.execute("""
    INSERT OR IGNORE INTO main.reviewsegment (id, camera, start_time, end_time, severity, thumb_path, data)
    SELECT id, camera, start_time, end_time, severity, thumb_path, data
    FROM old.reviewsegment
""")
print(f"  Added {cursor.rowcount} entries")

# Import event
print("Importing event...")
cursor = conn.execute("""
    INSERT OR IGNORE INTO main.event
    SELECT * FROM old.event
""")
print(f"  Added {cursor.rowcount} entries")

conn.commit()

# Verify
print("\nFinal counts:")
for table in ['recordings', 'reviewsegment', 'event']:
    count = conn.execute(f"SELECT COUNT(*) FROM main.{table}").fetchone()[0]
    print(f"  {table}: {count}")

# Integrity check
print("\nIntegrity check...")
result = conn.execute("PRAGMA integrity_check").fetchone()[0]
print(f"  {result}")

conn.close()
PYTHON
else
    echo "Step 4: Using existing merged database"
fi
echo ""

# Step 5: Get new pod
echo "Step 5: Getting Frigate pod..."
POD=$(KUBECONFIG="$KUBECONFIG" kubectl get pods -n "$NAMESPACE" -l app=frigate -o jsonpath='{.items[0].metadata.name}')
echo "  Pod: $POD"
echo ""

# Step 6: Copy using cat instead of kubectl cp (more reliable)
echo "Step 6: Copying database to pod (using reliable method)..."
# Encode as base64 and decode in pod to avoid transfer issues
base64 < /tmp/frigate-merged.db > /tmp/frigate-merged.db.b64
KUBECONFIG="$KUBECONFIG" kubectl exec -n "$NAMESPACE" "$POD" -- sh -c 'cat > /tmp/frigate.db.b64' < /tmp/frigate-merged.db.b64
KUBECONFIG="$KUBECONFIG" kubectl exec -n "$NAMESPACE" "$POD" -- sh -c 'base64 -d /tmp/frigate.db.b64 > /config/frigate.db && rm /tmp/frigate.db.b64'
rm /tmp/frigate-merged.db.b64
echo "  Done"
echo ""

# Step 7: Verify in pod
echo "Step 7: Verifying database in pod..."
KUBECONFIG="$KUBECONFIG" kubectl exec -n "$NAMESPACE" "$POD" -- python3 -c "
import sqlite3
conn = sqlite3.connect('/config/frigate.db')
print('Integrity:', conn.execute('PRAGMA integrity_check').fetchone()[0])
for t in ['recordings', 'reviewsegment', 'event']:
    c = conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
    print(f'{t}: {c}')
"
echo ""

# Step 8: Restart pod
echo "Step 8: Restarting Frigate..."
KUBECONFIG="$KUBECONFIG" kubectl delete pod -n "$NAMESPACE" "$POD"
sleep 5
KUBECONFIG="$KUBECONFIG" kubectl wait --for=condition=Ready pod -l app=frigate -n "$NAMESPACE" --timeout=180s
echo ""

echo "========================================="
echo -e "${GREEN}Database restored!${NC}"
echo "========================================="
echo ""
echo "Check: http://frigate.app.homelab/review"
