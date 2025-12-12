#!/bin/bash
#
# 10-fix-recording-paths.sh
#
# Fix recording paths in database and symlinks so old recordings appear in UI.
#
# Problem: Database entries point to /import/recordings/ but Frigate UI
# looks for recordings at /media/frigate/recordings/
#
# Solution:
# 1. Fix symlinks in /media/frigate/recordings/ to point to /import/recordings/
# 2. Update database paths from /import/recordings/ to /media/frigate/recordings/
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"
NAMESPACE="frigate"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "========================================="
echo "Fix Frigate Recording Paths"
echo "========================================="
echo ""

# Get pod name
POD=$(KUBECONFIG="$KUBECONFIG" kubectl get pods -n "$NAMESPACE" -l app=frigate -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [[ -z "$POD" ]]; then
    echo "ERROR: No Frigate pod found"
    exit 1
fi
echo "Pod: $POD"
echo ""

# Copy and run the Python fix script
cat > /tmp/fix-paths.py << 'PYTHON_SCRIPT'
#!/usr/bin/env python3
"""Fix recording paths in database and symlinks."""

import os
import sqlite3

def fix_symlinks():
    """Fix symlinks to point to correct /import/recordings/ path."""
    rec_dir = '/media/frigate/recordings'
    fixed = 0

    print("Step 1: Fixing symlinks...")
    for item in os.listdir(rec_dir):
        full_path = os.path.join(rec_dir, item)
        if os.path.islink(full_path):
            old_target = os.readlink(full_path)
            if '/import/frigate/recordings/' in old_target:
                new_target = old_target.replace('/import/frigate/recordings/', '/import/recordings/')
                os.unlink(full_path)
                os.symlink(new_target, full_path)
                fixed += 1
                print(f"  Fixed: {item} -> {new_target}")

    print(f"  Total symlinks fixed: {fixed}")
    return fixed

def fix_database_paths():
    """Update database paths from /import/ to /media/frigate/."""
    conn = sqlite3.connect('/config/frigate.db')

    print("")
    print("Step 2: Checking database...")

    # Count paths
    import_count = conn.execute("SELECT COUNT(*) FROM recordings WHERE path LIKE '/import/%'").fetchone()[0]
    media_count = conn.execute("SELECT COUNT(*) FROM recordings WHERE path LIKE '/media/frigate/%'").fetchone()[0]
    print(f"  /import/ paths: {import_count}")
    print(f"  /media/frigate/ paths: {media_count}")

    if import_count == 0:
        print("  No /import/ paths to fix")
        return 0

    # Check for conflicts (same file in both locations)
    conflicts = conn.execute("""
        SELECT COUNT(*) FROM recordings r1
        WHERE r1.path LIKE '/import/recordings/%'
        AND EXISTS (
            SELECT 1 FROM recordings r2
            WHERE r2.path = REPLACE(r1.path, '/import/recordings/', '/media/frigate/recordings/')
        )
    """).fetchone()[0]

    print(f"  Conflicting paths: {conflicts}")

    # Delete duplicates if any
    if conflicts > 0:
        print("")
        print("Step 3: Removing duplicate entries...")
        cursor = conn.execute("""
            DELETE FROM recordings
            WHERE path LIKE '/import/recordings/%'
            AND REPLACE(path, '/import/recordings/', '/media/frigate/recordings/') IN (
                SELECT path FROM recordings WHERE path LIKE '/media/frigate/recordings/%'
            )
        """)
        print(f"  Deleted {cursor.rowcount} duplicates")
        conn.commit()

    # Update remaining paths
    print("")
    print("Step 4: Updating paths...")
    cursor = conn.execute("""
        UPDATE recordings
        SET path = REPLACE(path, '/import/recordings/', '/media/frigate/recordings/')
        WHERE path LIKE '/import/recordings/%'
    """)
    updated = cursor.rowcount
    print(f"  Updated {updated} paths")
    conn.commit()

    # Final verification
    print("")
    print("Step 5: Verification...")
    import_count = conn.execute("SELECT COUNT(*) FROM recordings WHERE path LIKE '/import/%'").fetchone()[0]
    media_count = conn.execute("SELECT COUNT(*) FROM recordings WHERE path LIKE '/media/frigate/%'").fetchone()[0]
    print(f"  /import/ paths remaining: {import_count}")
    print(f"  /media/frigate/ paths total: {media_count}")

    # Test a file exists
    print("")
    print("Step 6: File existence test...")
    row = conn.execute("SELECT path FROM recordings WHERE path LIKE '/media/frigate/recordings/2025-05%' LIMIT 1").fetchone()
    if row:
        path = row[0]
        exists = os.path.exists(path)
        print(f"  {path[-50:]}: {'EXISTS' if exists else 'MISSING'}")

    conn.close()
    return updated

def main():
    fix_symlinks()
    fix_database_paths()
    print("")
    print("Done!")
    return 0

if __name__ == "__main__":
    exit(main())
PYTHON_SCRIPT

echo "Copying fix script to pod..."
KUBECONFIG="$KUBECONFIG" kubectl cp /tmp/fix-paths.py "$NAMESPACE/$POD:/tmp/fix-paths.py"
echo ""

echo "Running fix script..."
echo "----------------------------------------"
KUBECONFIG="$KUBECONFIG" kubectl exec -n "$NAMESPACE" "$POD" -- python3 /tmp/fix-paths.py
echo "----------------------------------------"
echo ""

# Cleanup
KUBECONFIG="$KUBECONFIG" kubectl exec -n "$NAMESPACE" "$POD" -- rm -f /tmp/fix-paths.py
rm -f /tmp/fix-paths.py

echo ""
echo "========================================="
echo -e "${GREEN}Path fix complete!${NC}"
echo "========================================="
echo ""
echo "Verify in UI: http://frigate.app.homelab"
