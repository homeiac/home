#!/bin/bash
#
# 13-merge-databases.sh
#
# Merge old frigate.db (from PBS backup) with current K8s Frigate database.
# This imports reviewsegment entries so old recordings appear in Review UI.
#
# Prerequisites:
# - Run 12-restore-db-from-pbs.sh first to extract old DB to pumped-piglet:/tmp/frigate-old.db
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"
NAMESPACE="frigate"
HOST="pumped-piglet.maas"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "========================================="
echo "Merge Frigate Databases"
echo "========================================="
echo ""

# Step 1: Copy old DB locally
echo "Step 1: Copying old database from $HOST..."
scp root@$HOST:/tmp/frigate-old.db /tmp/frigate-old.db
ls -la /tmp/frigate-old.db
echo ""

# Step 2: Check old database contents
echo "Step 2: Old database contents..."
sqlite3 /tmp/frigate-old.db << 'SQL'
.headers on
SELECT 'Recordings' as table_name, COUNT(*) as count FROM recordings
UNION ALL SELECT 'ReviewSegments', COUNT(*) FROM reviewsegment
UNION ALL SELECT 'Events', COUNT(*) FROM event
UNION ALL SELECT 'Timeline', COUNT(*) FROM timeline
UNION ALL SELECT 'Previews', COUNT(*) FROM previews;
SQL
echo ""

# Step 3: Get pod name and backup current DB
echo "Step 3: Getting K8s pod and backing up current database..."
POD=$(KUBECONFIG="$KUBECONFIG" kubectl get pods -n "$NAMESPACE" -l app=frigate -o jsonpath='{.items[0].metadata.name}')
echo "  Pod: $POD"

KUBECONFIG="$KUBECONFIG" kubectl cp "$NAMESPACE/$POD:/config/frigate.db" /tmp/frigate-k8s-backup.db
echo "  Backed up current DB to /tmp/frigate-k8s-backup.db"
echo ""

# Step 4: Check current K8s database
echo "Step 4: Current K8s database contents..."
sqlite3 /tmp/frigate-k8s-backup.db << 'SQL'
.headers on
SELECT 'Recordings' as table_name, COUNT(*) as count FROM recordings
UNION ALL SELECT 'ReviewSegments', COUNT(*) FROM reviewsegment
UNION ALL SELECT 'Events', COUNT(*) FROM event;
SQL
echo ""

# Step 5: Create merge script
echo "Step 5: Creating merge script..."
cat > /tmp/merge-frigate-db.py << 'PYTHON'
#!/usr/bin/env python3
"""
Merge old Frigate database into current one.
Imports: reviewsegment, event, timeline, previews
Updates: recordings paths from old format to new /media/frigate/ format
"""

import sqlite3
import json
import os

OLD_DB = "/tmp/frigate-old.db"
CURRENT_DB = "/tmp/frigate-k8s-backup.db"
OUTPUT_DB = "/tmp/frigate-merged.db"

# Path mapping: old paths need to be updated to new mount point
# Old: /media/frigate/recordings/... (in LXC)
# New: /media/frigate/recordings/... (in K8s - same, but via symlinks to /import/)

def main():
    print("Opening databases...")

    # Copy current DB as base
    os.system(f"cp {CURRENT_DB} {OUTPUT_DB}")

    conn = sqlite3.connect(OUTPUT_DB)
    conn.execute("ATTACH DATABASE ? AS old", (OLD_DB,))

    # Get current counts
    print("\nCurrent state:")
    for table in ['recordings', 'reviewsegment', 'event', 'timeline', 'previews']:
        try:
            count = conn.execute(f"SELECT COUNT(*) FROM main.{table}").fetchone()[0]
            old_count = conn.execute(f"SELECT COUNT(*) FROM old.{table}").fetchone()[0]
            print(f"  {table}: current={count}, old={old_count}")
        except:
            pass

    # Import reviewsegment entries (the key for Review UI)
    print("\nImporting reviewsegment entries...")
    cursor = conn.execute("""
        INSERT OR IGNORE INTO main.reviewsegment (id, camera, start_time, end_time, severity, thumb_path, data)
        SELECT id, camera, start_time, end_time, severity, thumb_path, data
        FROM old.reviewsegment
    """)
    print(f"  Imported {cursor.rowcount} reviewsegment entries")

    # Import event entries
    print("\nImporting event entries...")
    cursor = conn.execute("""
        INSERT OR IGNORE INTO main.event
        SELECT * FROM old.event
    """)
    print(f"  Imported {cursor.rowcount} event entries")

    # Import timeline entries
    print("\nImporting timeline entries...")
    try:
        cursor = conn.execute("""
            INSERT OR IGNORE INTO main.timeline
            SELECT * FROM old.timeline
        """)
        print(f"  Imported {cursor.rowcount} timeline entries")
    except Exception as e:
        print(f"  Skipped timeline: {e}")

    # Import previews
    print("\nImporting preview entries...")
    try:
        cursor = conn.execute("""
            INSERT OR IGNORE INTO main.previews
            SELECT * FROM old.previews
        """)
        print(f"  Imported {cursor.rowcount} preview entries")
    except Exception as e:
        print(f"  Skipped previews: {e}")

    conn.commit()

    # Final counts
    print("\nFinal state:")
    for table in ['recordings', 'reviewsegment', 'event']:
        count = conn.execute(f"SELECT COUNT(*) FROM main.{table}").fetchone()[0]
        print(f"  {table}: {count}")

    conn.close()
    print(f"\nMerged database saved to: {OUTPUT_DB}")

if __name__ == "__main__":
    main()
PYTHON

python3 /tmp/merge-frigate-db.py
echo ""

# Step 6: Verify merged database
echo "Step 6: Verifying merged database..."
sqlite3 /tmp/frigate-merged.db << 'SQL'
.headers on
SELECT 'Recordings' as table_name, COUNT(*) as count FROM recordings
UNION ALL SELECT 'ReviewSegments', COUNT(*) FROM reviewsegment
UNION ALL SELECT 'Events', COUNT(*) FROM event;
SQL
echo ""

# Step 7: Copy merged DB to pod
echo "Step 7: Copying merged database to Frigate pod..."
KUBECONFIG="$KUBECONFIG" kubectl cp /tmp/frigate-merged.db "$NAMESPACE/$POD:/config/frigate.db"
echo "  Done"
echo ""

# Step 8: Restart Frigate to pick up new DB
echo "Step 8: Restarting Frigate pod..."
KUBECONFIG="$KUBECONFIG" kubectl delete pod -n "$NAMESPACE" "$POD"
echo "  Waiting for new pod..."
sleep 5
KUBECONFIG="$KUBECONFIG" kubectl wait --for=condition=Ready pod -l app=frigate -n "$NAMESPACE" --timeout=120s
echo ""

# Step 9: Cleanup temp container
echo "Step 9: Cleaning up temporary container 9113..."
ssh root@$HOST "pct destroy 9113 --force 2>/dev/null || true"
echo ""

echo "========================================="
echo -e "${GREEN}Database merge complete!${NC}"
echo "========================================="
echo ""
echo "Check: http://frigate.app.homelab/review"
