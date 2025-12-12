#!/bin/bash
#
# 08-run-import.sh
#
# Run the Python import script inside the Frigate pod to import
# old recordings into the database.
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"
NAMESPACE="frigate"
DEPLOYMENT="frigate"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "========================================="
echo "Import Old Frigate Recordings"
echo "========================================="
echo ""

# Get pod name
echo "Step 1: Finding Frigate pod..."
POD=$(KUBECONFIG="$KUBECONFIG" kubectl get pods -n "$NAMESPACE" -l app=frigate -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [[ -z "$POD" ]]; then
    echo "ERROR: No Frigate pod found"
    exit 1
fi
echo "  Pod: $POD"
echo ""

# Get current recording count
echo "Step 2: Current database state..."
BEFORE_COUNT=$(KUBECONFIG="$KUBECONFIG" kubectl exec -n "$NAMESPACE" "$POD" -- \
    python3 -c "import sqlite3; print(sqlite3.connect('/config/frigate.db').execute('SELECT COUNT(*) FROM recordings').fetchone()[0])" 2>/dev/null || echo "0")
echo "  Recordings in DB: $BEFORE_COUNT"
echo ""

# Copy Python script to pod
echo "Step 3: Copying import script to pod..."
KUBECONFIG="$KUBECONFIG" kubectl cp "$SCRIPT_DIR/import-old-recordings.py" "$NAMESPACE/$POD:/tmp/import-old-recordings.py"
echo "  Copied to /tmp/import-old-recordings.py"
echo ""

# Run import script
echo "Step 4: Running import..."
echo "----------------------------------------"
KUBECONFIG="$KUBECONFIG" kubectl exec -n "$NAMESPACE" "$POD" -- python3 /tmp/import-old-recordings.py
echo "----------------------------------------"
echo ""

# Get new recording count
echo "Step 5: Final database state..."
AFTER_COUNT=$(KUBECONFIG="$KUBECONFIG" kubectl exec -n "$NAMESPACE" "$POD" -- \
    python3 -c "import sqlite3; print(sqlite3.connect('/config/frigate.db').execute('SELECT COUNT(*) FROM recordings').fetchone()[0])" 2>/dev/null || echo "0")
echo "  Recordings in DB: $AFTER_COUNT"
echo "  New recordings: $((AFTER_COUNT - BEFORE_COUNT))"
echo ""

# Clean up
echo "Step 6: Cleanup..."
KUBECONFIG="$KUBECONFIG" kubectl exec -n "$NAMESPACE" "$POD" -- rm -f /tmp/import-old-recordings.py
echo "  Removed temporary script"
echo ""

echo "========================================="
echo -e "${GREEN}Import complete!${NC}"
echo "========================================="
echo ""
echo "Verify in UI: http://frigate.app.homelab"
echo "Or run: ./09-verify-import.sh"
