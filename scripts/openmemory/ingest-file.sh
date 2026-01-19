#!/bin/bash
# Ingest a single file into OpenMemory
# Usage: ./ingest-file.sh <file>

set -e

if [[ -z "$1" ]]; then
    echo "Usage: $0 <file>"
    exit 1
fi

FILE="$1"
OPENMEMORY_URL="${OPENMEMORY_URL:-http://localhost:8080}"

if [[ ! -f "$FILE" ]]; then
    echo "Error: File not found: $FILE"
    exit 1
fi

# Get content type from extension
case "${FILE##*.}" in
    md|markdown) CT="md" ;;
    sh|bash) CT="txt" ;;
    yaml|yml) CT="txt" ;;
    txt) CT="txt" ;;
    html|htm) CT="html" ;;
    *) CT="txt" ;;
esac

# Get category from path
case "$FILE" in
    */docs/*) CAT="documentation" ;;
    */scripts/*) CAT="script" ;;
    */k8s/*) CAT="k8s-config" ;;
    */gitops/*) CAT="gitops" ;;
    */proxmox/*) CAT="proxmox" ;;
    *CLAUDE.md) CAT="claude-instructions" ;;
    *) CAT="other" ;;
esac

FILENAME=$(basename "$FILE")

# Create temp file for content (handles escaping properly)
TMPFILE=$(mktemp)
trap "rm -f $TMPFILE" EXIT

# Build payload
jq -n --rawfile data "$FILE" \
    --arg ct "$CT" \
    --arg path "$FILE" \
    --arg name "$FILENAME" \
    --arg cat "$CAT" \
    '{
        content_type: $ct,
        data: $data,
        metadata: {
            source: "file",
            path: $path,
            filename: $name,
            category: $cat,
            repo: "home",
            ingested_by: "ingest-file.sh"
        }
    }' > "$TMPFILE"

# Send to API
RESPONSE=$(curl -s -X POST "$OPENMEMORY_URL/memory/ingest" \
    -H "Content-Type: application/json" \
    -d @"$TMPFILE")

# Check result
if echo "$RESPONSE" | jq -e '.root_memory_id' > /dev/null 2>&1; then
    ID=$(echo "$RESPONSE" | jq -r '.root_memory_id')
    STRATEGY=$(echo "$RESPONSE" | jq -r '.strategy')
    CHILDREN=$(echo "$RESPONSE" | jq -r '.child_count')
    TOKENS=$(echo "$RESPONSE" | jq -r '.total_tokens')

    echo "Success!"
    echo "  ID:       $ID"
    echo "  Strategy: $STRATEGY"
    echo "  Children: $CHILDREN"
    echo "  Tokens:   $TOKENS"
else
    echo "Error:"
    echo "$RESPONSE" | jq .
    exit 1
fi
