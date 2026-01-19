#!/bin/bash
# Ingest all files in a folder into OpenMemory
# Usage: ./ingest-folder.sh <folder> [pattern]
#
# Examples:
#   ./ingest-folder.sh scripts/haos          # All files
#   ./ingest-folder.sh scripts/haos "*.sh"   # Only .sh files

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FOLDER="${1:?Usage: $0 <folder> [pattern]}"
PATTERN="${2:-*}"

if [[ ! -d "$FOLDER" ]]; then
    echo "Error: Folder not found: $FOLDER"
    exit 1
fi

# Count files
FILES=$(find "$FOLDER" -maxdepth 1 -type f -name "$PATTERN" | wc -l | tr -d ' ')
echo "=== Ingesting $FILES files from $FOLDER ==="
echo ""

SUCCESS=0
FAILED=0

for f in "$FOLDER"/$PATTERN; do
    [[ -f "$f" ]] || continue

    BASENAME=$(basename "$f")
    echo -n "[$((SUCCESS + FAILED + 1))/$FILES] $BASENAME... "

    OUTPUT=$("$SCRIPT_DIR/ingest-file.sh" "$f" 2>&1)

    if echo "$OUTPUT" | grep -q "Success"; then
        ID=$(echo "$OUTPUT" | grep "ID:" | awk '{print $2}')
        echo "OK ($ID)"
        ((SUCCESS++))
    else
        echo "FAILED"
        echo "$OUTPUT" | head -3
        ((FAILED++))
    fi
done

echo ""
echo "=== Complete ==="
echo "Success: $SUCCESS"
echo "Failed:  $FAILED"
