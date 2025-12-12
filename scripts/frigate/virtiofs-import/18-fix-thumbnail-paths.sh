#!/bin/bash
#
# 18-fix-thumbnail-paths.sh
#
# Fix thumbnail paths by symlinking old clips into the media directory.
# Old thumbnails are at /import/clips/review/
# Frigate expects them at /media/frigate/clips/review/
#

set -euo pipefail

KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"
NAMESPACE="frigate"

# Colors
GREEN='\033[0;32m'
NC='\033[0m'

echo "========================================="
echo "Fix Thumbnail Paths"
echo "========================================="
echo ""

POD=$(KUBECONFIG="$KUBECONFIG" kubectl get pods -n "$NAMESPACE" -l app=frigate -o jsonpath='{.items[0].metadata.name}')
echo "Pod: $POD"
echo ""

# Step 1: Check current state
echo "Step 1: Current state..."
KUBECONFIG="$KUBECONFIG" kubectl exec -n "$NAMESPACE" "$POD" -- bash -c '
echo "Old thumbs at /import/clips/review/: $(ls /import/clips/review/*.webp 2>/dev/null | wc -l)"
echo "New thumbs at /media/frigate/clips/review/: $(ls /media/frigate/clips/review/*.webp 2>/dev/null | wc -l)"
'
echo ""

# Step 2: Symlink old thumbnails into media directory
echo "Step 2: Creating symlinks for old thumbnails..."
KUBECONFIG="$KUBECONFIG" kubectl exec -n "$NAMESPACE" "$POD" -- bash -c '
cd /media/frigate/clips/review/
count=0
for f in /import/clips/review/*.webp; do
    fname=$(basename "$f")
    if [ ! -e "$fname" ]; then
        ln -s "$f" "$fname"
        count=$((count + 1))
    fi
done
echo "Created $count symlinks"
echo "Total files now: $(ls -la | wc -l)"
'
echo ""

# Step 3: Verify a sample thumbnail loads
echo "Step 3: Verifying sample thumbnail..."
KUBECONFIG="$KUBECONFIG" kubectl exec -n "$NAMESPACE" "$POD" -- bash -c '
# Get first old reviewsegment thumb_path
sample=$(sqlite3 /config/frigate.db "SELECT thumb_path FROM reviewsegment WHERE thumb_path LIKE \"%1754%\" LIMIT 1" 2>/dev/null)
echo "Sample path: $sample"
if [ -f "$sample" ] || [ -L "$sample" ]; then
    echo "Status: EXISTS"
    ls -la "$sample"
else
    echo "Status: MISSING"
fi
'
echo ""

echo "========================================="
echo -e "${GREEN}Thumbnail symlinks created!${NC}"
echo "========================================="
echo ""
echo "Refresh: http://frigate.app.homelab/review"
