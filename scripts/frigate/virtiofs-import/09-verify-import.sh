#!/bin/bash
#
# 09-verify-import.sh
#
# Verify that old recordings were imported successfully
#

set -euo pipefail

KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"
NAMESPACE="frigate"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "========================================="
echo "Verify Frigate Recording Import"
echo "========================================="
echo ""

# Get pod name
POD=$(KUBECONFIG="$KUBECONFIG" kubectl get pods -n "$NAMESPACE" -l app=frigate -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [[ -z "$POD" ]]; then
    echo "ERROR: No Frigate pod found"
    exit 1
fi

# Total recording count
echo "Recording Statistics:"
echo "---------------------"
TOTAL=$(KUBECONFIG="$KUBECONFIG" kubectl exec -n "$NAMESPACE" "$POD" -- \
    python3 -c "import sqlite3; print(sqlite3.connect('/config/frigate.db').execute('SELECT COUNT(*) FROM recordings').fetchone()[0])")
echo "  Total recordings: $TOTAL"

# Count by camera
echo ""
echo "By Camera:"
KUBECONFIG="$KUBECONFIG" kubectl exec -n "$NAMESPACE" "$POD" -- \
    python3 -c "
import sqlite3
conn = sqlite3.connect('/config/frigate.db')
for row in conn.execute('SELECT camera, COUNT(*) FROM recordings GROUP BY camera ORDER BY camera'):
    print(f'  {row[0]}: {row[1]}')
"

# Date range
echo ""
echo "Date Range:"
KUBECONFIG="$KUBECONFIG" kubectl exec -n "$NAMESPACE" "$POD" -- \
    python3 -c "
import sqlite3
from datetime import datetime
conn = sqlite3.connect('/config/frigate.db')
row = conn.execute('SELECT MIN(start_time), MAX(start_time) FROM recordings').fetchone()
if row[0] and row[1]:
    min_dt = datetime.utcfromtimestamp(row[0]).strftime('%Y-%m-%d %H:%M:%S')
    max_dt = datetime.utcfromtimestamp(row[1]).strftime('%Y-%m-%d %H:%M:%S')
    print(f'  Oldest: {min_dt} UTC')
    print(f'  Newest: {max_dt} UTC')
"

# Sample recordings from import path
echo ""
echo "Sample Imported Recordings:"
KUBECONFIG="$KUBECONFIG" kubectl exec -n "$NAMESPACE" "$POD" -- \
    python3 -c "
import sqlite3
conn = sqlite3.connect('/config/frigate.db')
for row in conn.execute(\"SELECT camera, path, datetime(start_time, 'unixepoch') FROM recordings WHERE path LIKE '/import/%' ORDER BY start_time LIMIT 5\"):
    print(f'  [{row[0]}] {row[2]}: {row[1][-40:]}')
" 2>/dev/null || echo "  (No /import/ recordings found)"

# Count imported vs new
echo ""
echo "Recording Sources:"
IMPORT_COUNT=$(KUBECONFIG="$KUBECONFIG" kubectl exec -n "$NAMESPACE" "$POD" -- \
    python3 -c "import sqlite3; print(sqlite3.connect('/config/frigate.db').execute(\"SELECT COUNT(*) FROM recordings WHERE path LIKE '/import/%'\").fetchone()[0])")
MEDIA_COUNT=$(KUBECONFIG="$KUBECONFIG" kubectl exec -n "$NAMESPACE" "$POD" -- \
    python3 -c "import sqlite3; print(sqlite3.connect('/config/frigate.db').execute(\"SELECT COUNT(*) FROM recordings WHERE path LIKE '/media/%'\").fetchone()[0])")
echo "  From /import/ (old): $IMPORT_COUNT"
echo "  From /media/ (new): $MEDIA_COUNT"

# Test API access
echo ""
echo "API Test:"
LB_IP=$(KUBECONFIG="$KUBECONFIG" kubectl get svc frigate -n "$NAMESPACE" -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null)
if [[ -n "$LB_IP" ]]; then
    VERSION=$(curl -s --max-time 5 "http://$LB_IP:5000/api/version" 2>/dev/null || echo "failed")
    echo "  LoadBalancer: $LB_IP"
    echo "  API response: $VERSION"
else
    echo "  LoadBalancer IP not found"
fi

echo ""
echo "========================================="
if [[ "$IMPORT_COUNT" -gt 0 ]]; then
    echo -e "${GREEN}Import verified! $IMPORT_COUNT old recordings in database.${NC}"
else
    echo -e "${YELLOW}No imported recordings found. Run 08-run-import.sh first.${NC}"
fi
echo "========================================="
echo ""
echo "View recordings: http://frigate.app.homelab"
